#!/usr/bin/env python3
"""Compact YOLO/depth detection pipeline for Colt."""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import cv2
import numpy as np
import rospy
import tf2_ros
from colt_msgs.msg import Detection3D
from geometry_msgs.msg import Point
from ultralytics import YOLO

from bridle_common import expand_centered_box, load_json, load_yaml, project_pixel, rotate_vector
from object_registry import ChairRegistry, child_object, object_position, shift_position, to_detection_message


MODEL_ORDER = ("chair", "chair_seat_roi", "aluminum_roi")
CLASS_TYPE = {
    "chair": "chair",
    "chair_seat": "seat",
    "aluminum_block": "item",
}
DRAW_COLORS = {
    "chair": (80, 220, 80),
    "seat": (0, 220, 255),
    "item": (0, 80, 255),
}


def _log(message):
    print(f"[colt] {message}", file=sys.stderr, flush=True)


def bbox_center(bbox):
    x1, y1, x2, y2 = bbox
    return int((x1 + x2) * 0.5), int((y1 + y2) * 0.5)


def center_window_region(shape, bbox, radius=3):
    height, width = shape[:2]
    center_x, center_y = bbox_center(bbox)
    region = np.zeros((height, width), dtype=bool)
    region[
        max(0, center_y - radius) : min(height, center_y + radius + 1),
        max(0, center_x - radius) : min(width, center_x + radius + 1),
    ] = True
    return region


def state_for(depth_valid, tf_ok, geometry_ok):
    if depth_valid and tf_ok and geometry_ok:
        return Detection3D.STATE_VISIBLE
    return Detection3D.STATE_VISIBLE_NO_DEPTH


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
        manifest_models = self.manifest.get("models", {})
        preprocess_models = self.preprocess.get("models", {})
        for name in MODEL_ORDER:
            manifest_model = manifest_models.get(name, {})
            preprocess_model = preprocess_models.get(name, {})
            classes = [str(item) for item in manifest_model.get("classes", [])]
            class_name = classes[0] if classes else name
            threshold = self.thresholds.get(class_name, {})
            models[name] = {
                "path": self.runtime_dir / manifest_model.get("file", f"{name}.onnx"),
                "input_size": int(preprocess_model.get("input_size", manifest_model.get("input_size", 640))),
                "classes": classes or [class_name],
                "confidence": float(threshold.get("confidence", 0.55)),
                "mask_min_area": int(threshold.get("mask_min_area", 0)),
            }
        return models

    def validate(self, load_onnx=False):
        errors = []
        for name in ("release_manifest.json", "preprocess.yaml", "thresholds.yaml", "roi_rules.yaml"):
            if not (self.runtime_dir / name).exists():
                errors.append(f"missing required file: {name}")
        for model_name in MODEL_ORDER:
            model_path = self.models[model_name]["path"]
            if not model_path.exists():
                errors.append(f"missing runtime model: {model_path.name}")

        if load_onnx and not errors:
            try:
                import onnxruntime as ort

                for model_name in MODEL_ORDER:
                    ort.InferenceSession(
                        str(self.models[model_name]["path"]),
                        providers=["CPUExecutionProvider"],
                    )
            except Exception as exc:
                errors.append(f"failed to load ONNX runtime model: {exc}")
        return errors

    def roi_rule(self, name):
        return self.roi_rules.get(name, {})


class SegModel:
    def __init__(self, name, spec):
        self.name = name
        self.classes = spec["classes"]
        self.input_size = int(spec["input_size"])
        self.confidence = float(spec["confidence"])
        self.mask_min_area = int(spec["mask_min_area"])
        _log(f"loading {name}: {Path(spec['path']).name}")
        started = time.monotonic()
        self.model = YOLO(str(spec["path"]), task="segment")
        _log(f"{name} loaded in {time.monotonic() - started:.1f}s")

    def predict(self, image):
        result = self.model.predict(
            source=image,
            imgsz=self.input_size,
            conf=self.confidence,
            iou=0.45,
            device="cpu",
            verbose=False,
        )
        if not result:
            return []
        result = result[0]
        if result.boxes is None or len(result.boxes) == 0:
            return []

        xyxy = result.boxes.xyxy.cpu().numpy()
        confidences = result.boxes.conf.cpu().numpy()
        class_ids = result.boxes.cls.cpu().numpy().astype(int)
        polygons = result.masks.xy if result.masks is not None else []

        items = []
        for index, bbox in enumerate(xyxy):
            class_id = int(class_ids[index])
            class_name = self.classes[class_id] if class_id < len(self.classes) else self.classes[0]
            mask = self._polygon_mask(image.shape[:2], polygons[index] if index < len(polygons) else None)
            if mask is not None and self.mask_min_area > 0 and int(np.count_nonzero(mask)) < self.mask_min_area:
                continue
            items.append(
                {
                    "bbox": bbox.astype(np.float32),
                    "confidence": float(confidences[index]),
                    "class_name": class_name,
                    "mask": mask,
                }
            )
        items.sort(key=lambda item: item["confidence"], reverse=True)
        return items

    def _polygon_mask(self, shape, polygon):
        if polygon is None or len(polygon) < 3:
            return None
        mask = np.zeros(shape, dtype=np.uint8)
        points = np.asarray(polygon, dtype=np.int32)
        cv2.fillPoly(mask, [points], 1)
        return mask.astype(bool)


class DetectionProjector:
    def __init__(self, target_frame, robot_frame, min_depth_pixels):
        self.target_frame = target_frame
        self.robot_frame = robot_frame
        self.min_depth_pixels = int(min_depth_pixels)
        self.tf_buffer = tf2_ros.Buffer(cache_time=rospy.Duration(5.0))
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer)

    def make_observation(self, item, depth, camera_info, image_header, parent=None):
        camera_point, depth_valid = self.estimate_point(item, depth, camera_info)
        point, frame_id, tf_ok = self.transform_to_target(camera_point, image_header, depth_valid)
        geometry_ok = self.geometry_ok(item["class_name"], point, parent)
        return {
            "object_type": CLASS_TYPE.get(item["class_name"], item["class_name"]),
            "bbox": tuple(int(value) for value in item["bbox"]),
            "confidence": float(item["confidence"]),
            "frame_id": frame_id,
            "x": float(point.x),
            "y": float(point.y),
            "z": float(point.z),
            "state": state_for(depth_valid, tf_ok, geometry_ok),
            "mask": item["mask"],
        }

    def estimate_point(self, item, depth, camera_info):
        depth_m = depth.astype(np.float32)
        if depth.dtype == np.uint16:
            depth_m *= 0.001

        valid = np.isfinite(depth_m) & (depth_m > 0.1) & (depth_m < 8.0)
        region = item["mask"] & valid if item["mask"] is not None else None
        if region is None or int(np.count_nonzero(region)) < self.min_depth_pixels:
            region = center_window_region(depth_m.shape, item["bbox"]) & valid

        if int(np.count_nonzero(region)) < self.min_depth_pixels:
            center_x, center_y = bbox_center(item["bbox"])
            return project_pixel(center_x, center_y, 0.0, camera_info), False

        ys, xs = np.nonzero(region)
        pixel_x = int(np.median(xs))
        pixel_y = int(np.median(ys))
        depth_z = float(np.median(depth_m[ys, xs]))
        return project_pixel(pixel_x, pixel_y, depth_z, camera_info), True

    def transform_to_target(self, point, image_header, depth_valid):
        if not depth_valid:
            return Point(), self.target_frame, False

        source_frame = image_header.frame_id
        if source_frame == self.target_frame:
            return point, self.target_frame, True

        direct, ok = self.transform_point(point, self.target_frame, source_frame, image_header.stamp)
        if ok:
            return direct, self.target_frame, True

        if self.robot_frame and self.robot_frame not in (source_frame, self.target_frame):
            robot_point, robot_ok = self.transform_point(point, self.robot_frame, source_frame, image_header.stamp)
            if robot_ok:
                world_point, world_ok = self.transform_point(robot_point, self.target_frame, self.robot_frame, image_header.stamp)
                if world_ok:
                    return world_point, self.target_frame, True

        return Point(), self.target_frame, False

    def transform_point(self, point, target_frame, source_frame, stamp):
        if source_frame == target_frame:
            return point, True
        transform = self.lookup_transform(target_frame, source_frame, stamp)
        if transform is None:
            return Point(), False
        rotated = rotate_vector([point.x, point.y, point.z], transform.transform.rotation)
        return (
            Point(
                x=float(rotated[0] + transform.transform.translation.x),
                y=float(rotated[1] + transform.transform.translation.y),
                z=float(rotated[2] + transform.transform.translation.z),
            ),
            True,
        )

    def lookup_transform(self, target_frame, source_frame, stamp):
        for lookup_stamp in (stamp, rospy.Time(0)):
            try:
                return self.tf_buffer.lookup_transform(
                    target_frame,
                    source_frame,
                    lookup_stamp,
                    timeout=rospy.Duration(0.05),
                )
            except Exception:
                pass
        rospy.logwarn_throttle(5.0, "Detector TF unavailable: %s <- %s", target_frame, source_frame)
        return None

    def geometry_ok(self, class_name, point, parent):
        if class_name == "chair" or parent is None:
            return True
        half_x = max(float(parent["bbox"][2] - parent["bbox"][0]) * 0.002 + 0.05, 0.05)
        half_y = max(float(parent["bbox"][3] - parent["bbox"][1]) * 0.002 + 0.05, 0.05)
        inside_parent = abs(float(point.x) - float(parent["x"])) <= half_x and abs(float(point.y) - float(parent["y"])) <= half_y
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

    def detect(self, color, depth, camera_info, image_header, selection):
        stamp = image_header.stamp if image_header.stamp != rospy.Time(0) else rospy.Time.now()
        chair_observations = [
            self.projector.make_observation(item, depth, camera_info, image_header)
            for item in self.models["chair"].predict(color)[: self.max_chairs]
        ]
        chair_objects, chair_states = self.chair_registry.update(chair_observations, selection, stamp)
        outputs = [self.output_item(chair, draw=chair.state != Detection3D.STATE_LOST) for chair in chair_objects]

        for role in ("source", "target"):
            chair = chair_states.get(selection.get(role, ""))
            if chair is None:
                continue
            seat = self.detect_tracked_child(
                parent=chair,
                object_type="seat",
                role=role,
                model_name="chair_seat_roi",
                image=color,
                depth=depth,
                camera_info=camera_info,
                image_header=image_header,
                rule_name="chair_roi",
                stamp=stamp,
            )
            outputs.append(self.output_item(seat, draw=seat.bbox is not None))

            if role != "source":
                continue
            item = self.detect_tracked_child(
                parent=seat,
                object_type="item",
                role="source",
                model_name="aluminum_roi",
                image=color,
                depth=depth,
                camera_info=camera_info,
                image_header=image_header,
                rule_name="seat_roi",
                stamp=stamp,
            )
            outputs.append(self.output_item(item, draw=item.bbox is not None))
        return outputs

    def detect_tracked_child(
        self,
        parent,
        object_type,
        role,
        model_name,
        image,
        depth,
        camera_info,
        image_header,
        rule_name,
        stamp,
    ):
        observation = None
        if parent is not None and parent.bbox is not None and int(parent.state) != Detection3D.STATE_LOST:
            observation = self.detect_child(
                model_name,
                image,
                depth,
                camera_info,
                image_header,
                parent.bbox,
                rule_name,
                self.object_state_dict(parent),
            )
        return self.track_child(parent, parent.object_id, object_type, role, observation, stamp)

    def detect_child(self, model_name, image, depth, camera_info, image_header, parent_bbox, rule_name, parent_observation):
        roi = expand_centered_box(
            image.shape[:2],
            parent_bbox,
            float(self.config.roi_rule(rule_name).get("expand_ratio", 0.2)),
            float(self.config.roi_rule(rule_name).get("min_width_px", 96)),
            float(self.config.roi_rule(rule_name).get("min_height_px", 96)),
        )
        x1, y1, x2, y2 = roi
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        predictions = self.models[model_name].predict(crop)
        if not predictions:
            return None
        item = self.map_roi_detection(predictions[0], roi, image.shape[:2])
        return self.projector.make_observation(item, depth, camera_info, image_header, parent=parent_observation)

    def map_roi_detection(self, item, roi, image_shape):
        x1, y1, x2, y2 = roi
        mask = None
        if item["mask"] is not None:
            mask = np.zeros(image_shape, dtype=bool)
            mask[y1:y2, x1:x2] = item["mask"]
        return {
            "bbox": np.array(
                [item["bbox"][0] + x1, item["bbox"][1] + y1, item["bbox"][2] + x1, item["bbox"][3] + y1],
                dtype=np.float32,
            ),
            "confidence": item["confidence"],
            "class_name": item["class_name"],
            "mask": mask,
        }

    def object_state_dict(self, obj):
        return {"x": obj.x, "y": obj.y, "z": obj.z, "bbox": obj.bbox}

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
            frame_id = parent.frame_id if parent is not None and parent.frame_id else self.projector.target_frame
        child = child_object(parent_id, object_type, role, state, confidence, frame_id, position, bbox, stamp)
        self.child_states[object_id] = child
        self.child_parent_positions[object_id] = self.parent_position(object_id, parent)
        return child

    def corrected_child_position(self, object_id, parent):
        current_parent_position = self.parent_position(object_id, parent)
        previous = self.child_states.get(object_id)
        if previous is None:
            return current_parent_position
        previous_parent_position = self.child_parent_positions.get(object_id, current_parent_position)
        delta = (
            current_parent_position[0] - previous_parent_position[0],
            current_parent_position[1] - previous_parent_position[1],
            current_parent_position[2] - previous_parent_position[2],
        )
        return shift_position(object_position(previous), delta)

    def parent_position(self, object_id, parent):
        if parent is not None:
            return object_position(parent)
        return self.child_parent_positions.get(object_id, (0.0, 0.0, 0.0))

    def output_item(self, obj, mask=None, draw=False):
        return {"message": to_detection_message(obj), "bbox": obj.bbox, "mask": mask, "draw": bool(draw)}

    def annotate(self, image, items):
        scene = image.copy()
        for item in items:
            if not item.get("draw") or item.get("bbox") is None:
                continue
            msg = item["message"]
            color = DRAW_COLORS.get(msg.object_type, (220, 220, 220))
            x1, y1, x2, y2 = [int(value) for value in item["bbox"]]
            if item.get("mask") is not None:
                overlay = scene.copy()
                overlay[item["mask"]] = color
                scene = cv2.addWeighted(overlay, 0.28, scene, 0.72, 0.0)
            cv2.rectangle(scene, (x1, y1), (x2, y2), color, 2)
            label = f"{msg.id} {msg.role or msg.object_type} {int(msg.state)}"
            cv2.putText(scene, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        return scene

    def check_result(self):
        errors = self.config.validate(load_onnx=True)
        return {"runtime_dir": str(self.config.runtime_dir), "errors": errors, "ready": not errors}
