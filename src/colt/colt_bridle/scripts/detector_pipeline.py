#!/usr/bin/env python3
"""Reusable runtime loading and stable object pipeline for Colt."""

import os
from pathlib import Path

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import numpy as np
import supervision as sv
import rospy
import tf2_ros
from colt_msgs.msg import Detection3D
from geometry_msgs.msg import Point
from ultralytics import YOLO

from bridle_detection import (
    bbox_center,
    center_window_region,
    map_roi_detection,
    object_type_for_class,
    roi_for_detection,
    state_for_detection,
    supervision_payload,
)
from bridle_common import load_json, load_yaml, project_pixel, rotate_vector
from object_registry import ChairRegistry, child_object, object_position, shift_position, to_detection_message


MODEL_ORDER = ("chair", "chair_seat_roi", "aluminum_roi")


class RuntimeConfig:
    def __init__(self, runtime_dir):
        self.runtime_dir = Path(runtime_dir).expanduser().resolve()
        self.manifest = load_json(self.runtime_dir / "release_manifest.json", {})
        self.preprocess = load_yaml(self.runtime_dir / "preprocess.yaml", {})
        self.thresholds = load_yaml(self.runtime_dir / "thresholds.yaml", {})
        self.roi_rules = load_yaml(self.runtime_dir / "roi_rules.yaml", {})
        self.models = self._build_models()

    def _build_models(self):
        models = {}
        preprocess_models = self.preprocess.get("models", {})
        manifest_models = self.manifest.get("models", {})
        for name in MODEL_ORDER:
            manifest_model = manifest_models.get(name, {})
            preprocess_model = preprocess_models.get(name, {})
            classes = [str(item) for item in manifest_model.get("classes", [])]
            models[name] = {
                "path": self.runtime_dir / manifest_model.get("file", f"{name}.onnx"),
                "input_size": int(
                    preprocess_model.get("input_size", manifest_model.get("input_size", 960))
                ),
                "classes": classes,
                "confidence": float(
                    self.thresholds.get(classes[0], {}).get("confidence", 0.55)
                )
                if classes
                else 0.55,
            }
        return models

    def validate(self):
        errors = []
        required = ("release_manifest.json", "preprocess.yaml", "thresholds.yaml", "roi_rules.yaml")
        for name in required:
            if not (self.runtime_dir / name).exists():
                errors.append(f"missing required file: {name}")
        for model_name in MODEL_ORDER:
            model_path = self.models[model_name]["path"]
            if not model_path.exists():
                errors.append(f"missing runtime model: {model_path.name}")
        return errors

    def roi_rule(self, name):
        return self.roi_rules.get(name, {})


class SegModel:
    def __init__(self, name, spec):
        self.name = name
        self.classes = spec["classes"] or [name]
        self.confidence = float(spec["confidence"])
        self.input_size = int(spec["input_size"])
        self.model = YOLO(Path(spec["path"]).as_posix(), task="segment", verbose=False)

    def predict(self, image):
        results = self.model.predict(
            source=image,
            imgsz=self.input_size,
            conf=self.confidence,
            iou=0.45,
            device="cpu",
            verbose=False,
        )
        if not results:
            return []

        detections = sv.Detections.from_ultralytics(results[0])
        items = []
        for index in range(len(detections.xyxy)):
            class_id = 0 if detections.class_id is None else int(detections.class_id[index])
            class_name = self.classes[class_id] if class_id < len(self.classes) else self.classes[0]
            mask = None if detections.mask is None else np.asarray(detections.mask[index]).astype(bool)
            items.append(
                {
                    "bbox": detections.xyxy[index].astype(np.float32),
                    "confidence": 0.0
                    if detections.confidence is None
                    else float(detections.confidence[index]),
                    "class_name": class_name,
                    "mask": mask,
                }
            )
        items.sort(key=lambda item: item["confidence"], reverse=True)
        return items


class DetectionProjector:
    def __init__(self, target_frame, robot_frame, min_depth_pixels):
        self.target_frame = target_frame
        self.robot_frame = robot_frame
        self.min_depth_pixels = int(min_depth_pixels)
        self.tf_buffer = tf2_ros.Buffer(cache_time=rospy.Duration(5.0))
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer)

    def make_observation(self, item, depth, camera_info, image_header, parent=None):
        point, depth_valid = self.estimate_point(item, depth, camera_info)
        point, frame_id, tf_ok = self.world_point(point, image_header, depth_valid)

        geometry_ok = self.geometry_ok(item["class_name"], point, parent)
        state = state_for_detection(depth_valid, tf_ok, geometry_ok)
        return {
            "object_type": object_type_for_class(item["class_name"]),
            "bbox": tuple(int(value) for value in item["bbox"]),
            "confidence": float(item["confidence"]),
            "frame_id": frame_id,
            "x": float(point.x),
            "y": float(point.y),
            "z": float(point.z),
            "state": state,
            "mask": item["mask"],
        }

    def world_point(self, point, image_header, depth_valid):
        if not depth_valid:
            return Point(x=0.0, y=0.0, z=0.0), self.target_frame, False

        robot_point, robot_ok = self.transform_point(
            point,
            target_frame=self.robot_frame,
            source_frame=image_header.frame_id,
            stamp=image_header.stamp,
        )
        if not robot_ok:
            return Point(x=0.0, y=0.0, z=0.0), self.target_frame, False

        world_point, world_ok = self.transform_point(
            robot_point,
            target_frame=self.target_frame,
            source_frame=self.robot_frame,
            stamp=image_header.stamp,
        )
        if not world_ok:
            return Point(x=0.0, y=0.0, z=0.0), self.target_frame, False
        return world_point, self.target_frame, True

    def estimate_point(self, item, depth, camera_info):
        depth_m = depth.astype(np.float32)
        if depth.dtype == np.uint16:
            depth_m *= 0.001

        valid = np.isfinite(depth_m) & (depth_m > 0.1) & (depth_m < 8.0)
        region = None if item["mask"] is None else item["mask"] & valid
        if region is None or int(np.count_nonzero(region)) < self.min_depth_pixels:
            region = center_window_region(depth.shape, item["bbox"]) & valid

        if int(np.count_nonzero(region)) < self.min_depth_pixels:
            center_x, center_y = bbox_center(item["bbox"])
            return project_pixel(center_x, center_y, 0.0, camera_info), False

        ys, xs = np.nonzero(region)
        pixel_x = int(np.median(xs))
        pixel_y = int(np.median(ys))
        depth_z = float(np.median(depth_m[ys, xs]))
        return project_pixel(pixel_x, pixel_y, depth_z, camera_info), True

    def transform_point(self, point, target_frame, source_frame, stamp):
        if source_frame == target_frame:
            return point, True
        transform = self.lookup_transform(target_frame, source_frame, stamp)
        if transform is None:
            return Point(x=0.0, y=0.0, z=0.0), False
        return self.apply_transform(point, transform), True

    def lookup_transform(self, target_frame, source_frame, stamp):
        try:
            return self.tf_buffer.lookup_transform(
                target_frame,
                source_frame,
                stamp,
                timeout=rospy.Duration(0.05),
            )
        except Exception:
            try:
                return self.tf_buffer.lookup_transform(
                    target_frame,
                    source_frame,
                    rospy.Time(0),
                    timeout=rospy.Duration(0.05),
                )
            except Exception as exc:
                rospy.logwarn_throttle(5.0, "Detector TF unavailable: %s", exc)
                return None

    def apply_transform(self, point, transform):
        rotated = rotate_vector([point.x, point.y, point.z], transform.transform.rotation)
        return Point(
            x=float(rotated[0] + transform.transform.translation.x),
            y=float(rotated[1] + transform.transform.translation.y),
            z=float(rotated[2] + transform.transform.translation.z),
        )

    def geometry_ok(self, class_name, point, parent):
        if class_name == "chair" or parent is None:
            return True
        half_x = max(float(parent["bbox"][2] - parent["bbox"][0]) * 0.002 + 0.05, 0.05)
        half_y = max(float(parent["bbox"][3] - parent["bbox"][1]) * 0.002 + 0.05, 0.05)
        inside_parent = (
            abs(float(point.x) - float(parent["x"])) <= half_x
            and abs(float(point.y) - float(parent["y"])) <= half_y
        )
        if class_name == "chair_seat":
            return inside_parent
        if class_name == "aluminum_block":
            return inside_parent and 0.0 <= float(point.z) - float(parent["z"]) <= 0.08
        return True


class DetectorPipeline:
    def __init__(
        self,
        runtime_dir,
        target_frame,
        robot_frame,
        max_chairs,
        min_depth_pixels,
        max_chair_match_distance,
    ):
        self.config = RuntimeConfig(runtime_dir)
        errors = self.config.validate()
        if errors:
            raise RuntimeError("; ".join(errors))

        self.models = {name: SegModel(name, self.config.models[name]) for name in MODEL_ORDER}
        self.projector = DetectionProjector(target_frame, robot_frame, min_depth_pixels)
        self.max_chairs = int(max_chairs)
        self.chair_registry = ChairRegistry(max_chair_match_distance)
        self.child_states = {}
        self.child_parent_positions = {}
        self.box_annotator = sv.BoxAnnotator()
        self.mask_annotator = sv.MaskAnnotator()
        self.label_annotator = sv.LabelAnnotator()

    def detect(self, color, depth, camera_info, image_header, selection):
        stamp = image_header.stamp if image_header.stamp != rospy.Time(0) else rospy.Time.now()
        chair_observations = self.detect_chairs(color, depth, camera_info, image_header)
        chair_objects, chair_states = self.chair_registry.update(chair_observations, selection, stamp)
        outputs = [self.output_item(chair, draw=chair.state != Detection3D.STATE_LOST) for chair in chair_objects]

        for role in ("source", "target"):
            chair_id = selection.get(role, "")
            if not chair_id:
                continue
            chair = chair_states.get(chair_id)
            if chair is None or chair.bbox is None or int(chair.state) == Detection3D.STATE_LOST:
                seat = self.track_child(parent=chair, parent_id=chair_id, object_type="seat", role=role, observation=None, stamp=stamp)
                outputs.append(self.output_item(seat))
                if role == "source":
                    item = self.track_child(parent=seat, parent_id=seat.object_id, object_type="item", role="source", observation=None, stamp=stamp)
                    outputs.append(self.output_item(item))
                continue

            seat_observation = self.detect_child(
                model_name="chair_seat_roi",
                image=color,
                depth=depth,
                camera_info=camera_info,
                image_header=image_header,
                parent_bbox=chair.bbox,
                rule_name="chair_roi",
                parent_observation=self.object_state_dict(chair),
            )
            seat = self.track_child(
                parent=chair,
                parent_id=chair.object_id,
                object_type="seat",
                role=role,
                observation=seat_observation,
                stamp=stamp,
            )
            outputs.append(
                self.output_item(
                    seat,
                    mask=None if seat_observation is None else seat_observation["mask"],
                    draw=seat_observation is not None,
                )
            )

            if role != "source":
                continue

            if seat.bbox is None or int(seat.state) == Detection3D.STATE_LOST:
                item = self.track_child(parent=seat, parent_id=seat.object_id, object_type="item", role="source", observation=None, stamp=stamp)
                outputs.append(self.output_item(item))
                continue

            item_observation = self.detect_child(
                model_name="aluminum_roi",
                image=color,
                depth=depth,
                camera_info=camera_info,
                image_header=image_header,
                parent_bbox=seat.bbox,
                rule_name="seat_roi",
                parent_observation=seat_observation,
            )
            item = self.track_child(
                parent=seat,
                parent_id=seat.object_id,
                object_type="item",
                role="source",
                observation=item_observation,
                stamp=stamp,
            )
            outputs.append(
                self.output_item(
                    item,
                    mask=None if item_observation is None else item_observation["mask"],
                    draw=item_observation is not None,
                )
            )

        return outputs

    def detect_chairs(self, color, depth, camera_info, image_header):
        chairs = self.models["chair"].predict(color)[: self.max_chairs]
        return [
            self.projector.make_observation(chair, depth, camera_info, image_header)
            for chair in chairs
        ]

    def detect_child(
        self,
        model_name,
        image,
        depth,
        camera_info,
        image_header,
        parent_bbox,
        rule_name,
        parent_observation,
    ):
        roi = roi_for_detection(image.shape[:2], parent_bbox, self.config.roi_rule(rule_name))
        x1, y1, x2, y2 = roi
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        predictions = self.models[model_name].predict(crop)
        if not predictions:
            return None
        mapped = map_roi_detection(predictions[0], roi, image.shape[:2])
        return self.projector.make_observation(
            mapped,
            depth,
            camera_info,
            image_header,
            parent=parent_observation,
        )

    def object_state_dict(self, obj):
        return {
            "x": obj.x,
            "y": obj.y,
            "z": obj.z,
            "bbox": obj.bbox,
        }

    def track_child(self, parent, parent_id, object_type, role, observation, stamp):
        object_id = f"{parent_id}_{object_type}"
        state = Detection3D.STATE_LOST if observation is None else int(observation["state"])
        confidence = 0.0 if observation is None else float(observation["confidence"])
        bbox = None if observation is None else observation["bbox"]
        if observation is not None and state == Detection3D.STATE_VISIBLE:
            position = (observation["x"], observation["y"], observation["z"])
            frame_id = observation["frame_id"]
        else:
            position = self.corrected_child_position(object_id, parent)
            frame_id = self.child_frame_id(parent, observation)
        child = child_object(
            parent_id=parent_id,
            object_type=object_type,
            role=role,
            state=state,
            confidence=confidence,
            frame_id=frame_id,
            position=position,
            bbox=bbox,
            stamp=stamp,
        )
        self.child_states[object_id] = child
        self.child_parent_positions[object_id] = (
            object_position(parent)
            if parent is not None
            else self.child_parent_positions.get(object_id, (0.0, 0.0, 0.0))
        )
        return child

    def corrected_child_position(self, object_id, parent):
        previous = self.child_states.get(object_id)
        current_parent_position = (
            object_position(parent)
            if parent is not None
            else self.child_parent_positions.get(object_id, (0.0, 0.0, 0.0))
        )
        if previous is None:
            return current_parent_position
        previous_parent_position = self.child_parent_positions.get(object_id, current_parent_position)
        delta = (
            current_parent_position[0] - previous_parent_position[0],
            current_parent_position[1] - previous_parent_position[1],
            current_parent_position[2] - previous_parent_position[2],
        )
        return shift_position(object_position(previous), delta)

    def child_frame_id(self, parent, observation):
        if parent is not None and parent.frame_id:
            return parent.frame_id
        if observation is not None:
            return observation["frame_id"]
        return self.projector.target_frame

    def output_item(self, obj, mask=None, draw=False):
        return {
            "message": to_detection_message(obj),
            "bbox": obj.bbox,
            "mask": mask,
            "draw": bool(draw),
        }

    def annotate(self, image, items):
        payload = supervision_payload(items)
        if payload[0] is None:
            return image
        detections, labels = payload
        scene = image.copy()
        if detections.mask is not None:
            scene = self.mask_annotator.annotate(scene, detections)
        scene = self.box_annotator.annotate(scene, detections)
        scene = self.label_annotator.annotate(scene, detections, labels=labels)
        return scene

    def check_result(self):
        errors = self.config.validate()
        return {
            "runtime_dir": str(self.config.runtime_dir),
            "errors": errors,
            "ready": not errors,
        }
