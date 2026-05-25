#!/usr/bin/env python3
"""Run the v001 three-stage ROI detector and publish Colt candidates."""

import json
import math
from pathlib import Path

import cv2
import message_filters
import numpy as np
import rospy
import tf2_ros
import yaml
from colt_msgs.msg import Detection3D, Detection3DArray
from geometry_msgs.msg import Point, PoseStamped, Quaternion, Vector3
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Header

try:
    import onnxruntime as ort
except ImportError:
    ort = None


MODEL_ORDER = ("chair", "chair_seat_roi", "aluminum_roi")


def load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def clamp(value, low, high):
    return max(low, min(high, value))


def rotate_vector(vector, quat):
    q = np.array([quat.x, quat.y, quat.z], dtype=np.float64)
    v = np.array(vector, dtype=np.float64)
    return v + 2.0 * np.cross(q, np.cross(q, v) + float(quat.w) * v)


def expand_box(box, ratio, min_width, min_height, width, height):
    x1, y1, x2, y2 = [float(v) for v in box]
    cx = (x1 + x2) * 0.5
    cy = (y1 + y2) * 0.5
    bw = max((x2 - x1) * (1.0 + ratio), float(min_width))
    bh = max((y2 - y1) * (1.0 + ratio), float(min_height))
    nx1 = int(math.floor(clamp(cx - bw * 0.5, 0, width - 1)))
    ny1 = int(math.floor(clamp(cy - bh * 0.5, 0, height - 1)))
    nx2 = int(math.ceil(clamp(cx + bw * 0.5, nx1 + 1, width)))
    ny2 = int(math.ceil(clamp(cy + bh * 0.5, ny1 + 1, height)))
    return (nx1, ny1, nx2, ny2)


def normalize_input_size(value, fallback):
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    if value:
        return int(value)
    return int(fallback)


def image_to_bgr8(msg):
    dtype = np.uint8
    channels = 3
    if msg.encoding in ("bgr8", "rgb8"):
        arr = np.frombuffer(msg.data, dtype=dtype).reshape(msg.height, msg.step)
        arr = arr[:, : msg.width * channels].reshape(msg.height, msg.width, channels)
        if msg.encoding == "rgb8":
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return np.ascontiguousarray(arr)
    if msg.encoding in ("mono8", "8UC1"):
        arr = np.frombuffer(msg.data, dtype=dtype).reshape(msg.height, msg.step)
        arr = arr[:, : msg.width]
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    raise ValueError(f"unsupported color image encoding: {msg.encoding}")


def image_to_depth(msg):
    if msg.encoding in ("16UC1", "mono16"):
        dtype = np.dtype(np.uint16)
    elif msg.encoding == "32FC1":
        dtype = np.dtype(np.float32)
    else:
        raise ValueError(f"unsupported depth image encoding: {msg.encoding}")
    if msg.is_bigendian != (dtype.byteorder == ">"):
        dtype = dtype.newbyteorder(">")
    item_size = dtype.itemsize
    arr = np.frombuffer(msg.data, dtype=dtype).reshape(msg.height, msg.step // item_size)
    return np.ascontiguousarray(arr[:, : msg.width])


def bgr8_to_image(image, header):
    msg = Image()
    msg.header = header
    msg.height = int(image.shape[0])
    msg.width = int(image.shape[1])
    msg.encoding = "bgr8"
    msg.is_bigendian = False
    msg.step = int(image.shape[1] * 3)
    msg.data = image.astype(np.uint8).tobytes()
    return msg


class RuntimeConfig:
    def __init__(self, runtime_dir):
        self.runtime_dir = Path(runtime_dir).expanduser().resolve()
        self.manifest = load_json(self.runtime_dir / "release_manifest.json")
        self.preprocess = load_yaml(self.runtime_dir / "preprocess.yaml")
        self.thresholds = load_yaml(self.runtime_dir / "thresholds.yaml")
        self.roi_rules = load_yaml(self.runtime_dir / "roi_rules.yaml")
        self.models = {}
        preprocess_models = self.preprocess.get("models", {})
        manifest_models = self.manifest.get("models", {})
        for name in MODEL_ORDER:
            model_data = manifest_models.get(name, {})
            prep_data = preprocess_models.get(name, {})
            file_name = model_data.get("file", f"{name}.onnx")
            classes = model_data.get("classes", [])
            self.models[name] = {
                "path": self.runtime_dir / file_name,
                "input_size": normalize_input_size(
                    prep_data.get("input_size"), model_data.get("input_size", 960)
                ),
                "classes": [str(item) for item in classes],
            }

    def confidence(self, class_name, default):
        return float(self.thresholds.get(class_name, {}).get("confidence", default))

    def min_area(self, class_name, default):
        return float(self.thresholds.get(class_name, {}).get("mask_min_area", default))

    def roi_rule(self, name):
        return self.roi_rules.get(name, {})


class YoloSegModel:
    def __init__(self, spec, backend):
        self.path = Path(spec["path"])
        self.input_size = int(spec["input_size"])
        self.classes = spec["classes"] or ["object"]
        self.backend = backend
        if backend == "onnxruntime":
            if ort is None:
                raise RuntimeError("onnxruntime is not installed")
            self.session = ort.InferenceSession(
                self.path.as_posix(), providers=["CPUExecutionProvider"]
            )
            self.input_name = self.session.get_inputs()[0].name
            self.net = None
            self.output_names = None
        elif backend == "cv2_dnn":
            self.net = cv2.dnn.readNetFromONNX(self.path.as_posix())
            self.output_names = self.net.getUnconnectedOutLayersNames()
            self.session = None
            self.input_name = ""
        else:
            raise ValueError(f"unsupported backend: {backend}")

    def letterbox(self, image):
        height, width = image.shape[:2]
        scale = min(self.input_size / float(width), self.input_size / float(height))
        new_width = int(round(width * scale))
        new_height = int(round(height * scale))
        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        pad_x = (self.input_size - new_width) // 2
        pad_y = (self.input_size - new_height) // 2
        canvas[pad_y : pad_y + new_height, pad_x : pad_x + new_width] = resized
        return canvas, scale, pad_x, pad_y

    def forward(self, image_bgr):
        model_image, scale, pad_x, pad_y = self.letterbox(image_bgr)
        blob = cv2.dnn.blobFromImage(
            model_image, scalefactor=1.0 / 255.0, size=(self.input_size, self.input_size),
            mean=(0, 0, 0), swapRB=True, crop=False
        )
        if self.backend == "onnxruntime":
            outputs = self.session.run(None, {self.input_name: blob})
        else:
            self.net.setInput(blob)
            outputs = self.net.forward(self.output_names)
        return outputs, scale, pad_x, pad_y

    def detect(self, image_bgr, conf_threshold, min_area, nms_threshold):
        outputs, scale, pad_x, pad_y = self.forward(image_bgr)
        pred, proto = self.split_outputs(outputs)
        if pred.size == 0 or proto is None:
            return []

        image_h, image_w = image_bgr.shape[:2]
        num_classes = max(len(self.classes), 1)
        mask_start = 4 + num_classes
        if pred.shape[1] <= mask_start:
            return []

        boxes = []
        scores = []
        class_ids = []
        coeffs = []
        for row in pred:
            class_scores = row[4:mask_start]
            class_id = int(np.argmax(class_scores))
            score = float(class_scores[class_id])
            if score < conf_threshold:
                continue
            cx, cy, bw, bh = [float(v) for v in row[:4]]
            x1 = (cx - bw * 0.5 - pad_x) / scale
            y1 = (cy - bh * 0.5 - pad_y) / scale
            x2 = (cx + bw * 0.5 - pad_x) / scale
            y2 = (cy + bh * 0.5 - pad_y) / scale
            x1 = clamp(x1, 0, image_w - 1)
            y1 = clamp(y1, 0, image_h - 1)
            x2 = clamp(x2, x1 + 1, image_w)
            y2 = clamp(y2, y1 + 1, image_h)
            boxes.append([int(x1), int(y1), int(x2 - x1), int(y2 - y1)])
            scores.append(score)
            class_ids.append(class_id)
            coeffs.append(row[mask_start:])

        keep = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, nms_threshold)
        if len(keep) == 0:
            return []
        keep = np.array(keep).reshape(-1).tolist()

        detections = []
        for index in keep:
            x, y, w, h = boxes[index]
            full_mask = self.build_mask(coeffs[index], proto, scale, pad_x, pad_y, image_w, image_h)
            mask = np.zeros((image_h, image_w), dtype=np.uint8)
            mask[y : y + h, x : x + w] = full_mask[y : y + h, x : x + w]
            area = float(cv2.countNonZero(mask))
            if area < min_area:
                continue
            class_id = class_ids[index]
            class_name = self.classes[class_id] if class_id < len(self.classes) else self.classes[0]
            detections.append(
                {
                    "bbox": (x, y, x + w, y + h),
                    "confidence": float(scores[index]),
                    "class_name": class_name,
                    "mask": mask,
                    "area": area,
                }
            )
        detections.sort(key=lambda item: item["confidence"], reverse=True)
        return detections

    def split_outputs(self, outputs):
        pred = None
        proto = None
        for output in outputs:
            arr = np.asarray(output)
            if arr.ndim == 3:
                pred = arr[0]
            elif arr.ndim == 4:
                proto = arr[0]
        if pred is None:
            return np.empty((0, 0), dtype=np.float32), None
        if pred.shape[0] < pred.shape[1] and pred.shape[0] <= 128:
            pred = pred.T
        return pred.astype(np.float32), proto.astype(np.float32) if proto is not None else None

    def build_mask(self, coeff, proto, scale, pad_x, pad_y, image_w, image_h):
        if proto.ndim != 3:
            return np.zeros((image_h, image_w), dtype=np.uint8)
        mask = sigmoid(np.matmul(coeff.astype(np.float32), proto.reshape(proto.shape[0], -1)))
        mask = mask.reshape(proto.shape[1], proto.shape[2])
        mask = cv2.resize(mask, (self.input_size, self.input_size), interpolation=cv2.INTER_LINEAR)
        x1 = int(pad_x)
        y1 = int(pad_y)
        x2 = int(round(pad_x + image_w * scale))
        y2 = int(round(pad_y + image_h * scale))
        mask = mask[y1:y2, x1:x2]
        mask = cv2.resize(mask, (image_w, image_h), interpolation=cv2.INTER_LINEAR)
        return (mask > 0.5).astype(np.uint8) * 255


class DetectorNode:
    def __init__(self):
        self.runtime_dir = rospy.get_param("~runtime_dir", "")
        if not self.runtime_dir:
            self.runtime_dir = Path(__file__).resolve().parents[1] / "models" / "runtime" / "current"
        self.target_frame = rospy.get_param("~target_frame", "base_footprint")
        self.backend = rospy.get_param("~backend", "auto")
        self.nms_threshold = float(rospy.get_param("~nms_threshold", 0.45))
        self.max_chairs = int(rospy.get_param("~max_chairs", 8))
        self.max_aluminum_per_seat = int(rospy.get_param("~max_aluminum_per_seat", 1))
        self.min_period = 1.0 / max(float(rospy.get_param("~detection_rate_hz", 1.0)), 0.1)
        self.last_process_time = rospy.Time(0)

        self.config = RuntimeConfig(self.runtime_dir)
        backend = self.resolve_backend()
        self.models = {name: YoloSegModel(self.config.models[name], backend) for name in MODEL_ORDER}
        self.tf_buffer = tf2_ros.Buffer(cache_time=rospy.Duration(5.0))
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer)

        self.candidates_pub = rospy.Publisher(
            "/colt/bridle/candidates", Detection3DArray, queue_size=1
        )
        self.debug_pub = rospy.Publisher("/colt/bridle/debug_image", Image, queue_size=1)

        color_topic = rospy.get_param("~color_topic", "/kinect2/qhd/image_color_rect")
        depth_topic = rospy.get_param("~depth_topic", "/kinect2/qhd/image_depth_rect")
        camera_info_topic = rospy.get_param("~camera_info_topic", "/kinect2/qhd/camera_info")
        queue_size = int(rospy.get_param("~sync_queue_size", 5))
        slop = float(rospy.get_param("~sync_slop", 0.08))
        color_sub = message_filters.Subscriber(color_topic, Image)
        depth_sub = message_filters.Subscriber(depth_topic, Image)
        info_sub = message_filters.Subscriber(camera_info_topic, CameraInfo)
        sync = message_filters.ApproximateTimeSynchronizer(
            [color_sub, depth_sub, info_sub], queue_size=queue_size, slop=slop
        )
        sync.registerCallback(self.frame_cb)
        self.sync = sync
        rospy.loginfo(
            "Colt detector ready: runtime=%s backend=%s target_frame=%s",
            self.config.runtime_dir,
            backend,
            self.target_frame,
        )

    def resolve_backend(self):
        if self.backend == "auto":
            if ort is None:
                raise RuntimeError("onnxruntime is required for v001 ONNX models")
            return "onnxruntime"
        return self.backend

    def frame_cb(self, color_msg, depth_msg, info_msg):
        now = rospy.Time.now()
        if (now - self.last_process_time).to_sec() < self.min_period:
            return
        self.last_process_time = now
        try:
            color = image_to_bgr8(color_msg)
            depth = image_to_depth(depth_msg)
            detections, debug = self.detect_frame(color, depth, info_msg, color_msg.header)
            out = Detection3DArray()
            out.header = Header(stamp=color_msg.header.stamp, frame_id=self.target_frame)
            if detections and detections[0].pose.header.frame_id != self.target_frame:
                out.header.frame_id = detections[0].pose.header.frame_id
            out.detections = detections
            out.scene_state = "candidate" if detections else "searching"
            self.candidates_pub.publish(out)
            self.debug_pub.publish(bgr8_to_image(debug, color_msg.header))
        except Exception as exc:
            rospy.logerr_throttle(5.0, "Colt detector frame failed: %s", exc)

    def detect_frame(self, color, depth, info_msg, header):
        debug = color.copy()
        output = []
        chair_items = self.models["chair"].detect(
            color,
            self.config.confidence("chair", 0.6),
            self.config.min_area("chair", 2000),
            self.nms_threshold,
        )[: self.max_chairs]

        for chair_index, chair in enumerate(chair_items):
            chair_id = f"chair_{chair_index}"
            output.append(self.make_detection(chair_id, chair, depth, info_msg, header))
            self.draw(debug, chair, (40, 220, 40), chair_id)

            chair_roi = self.crop_roi(color, chair["bbox"], self.config.roi_rule("chair_roi"))
            seat_items = self.detect_roi("chair_seat_roi", color, chair_roi)
            for seat_index, seat in enumerate(seat_items[:1]):
                seat_id = f"{chair_id}_seat" if seat_index == 0 else f"{chair_id}_seat_{seat_index}"
                output.append(self.make_detection(seat_id, seat, depth, info_msg, header))
                self.draw(debug, seat, (255, 190, 20), seat_id)

                seat_roi = self.crop_roi(color, seat["bbox"], self.config.roi_rule("seat_roi"))
                aluminum_items = self.detect_roi("aluminum_roi", color, seat_roi)
                for aluminum_index, aluminum in enumerate(
                    aluminum_items[: self.max_aluminum_per_seat]
                ):
                    aluminum_id = f"{seat_id}_aluminum_{aluminum_index}"
                    output.append(self.make_detection(aluminum_id, aluminum, depth, info_msg, header))
                    self.draw(debug, aluminum, (0, 0, 255), aluminum_id)
        return output, debug

    def crop_roi(self, image, bbox, rule):
        height, width = image.shape[:2]
        x1, y1, x2, y2 = expand_box(
            bbox,
            float(rule.get("expand_ratio", 0.2)),
            int(rule.get("min_width_px", 96)),
            int(rule.get("min_height_px", 96)),
            width,
            height,
        )
        return (x1, y1, x2, y2)

    def detect_roi(self, model_name, image, roi):
        x1, y1, x2, y2 = roi
        crop = image[y1:y2, x1:x2]
        class_name = self.config.models[model_name]["classes"][0]
        items = self.models[model_name].detect(
            crop,
            self.config.confidence(class_name, 0.6),
            self.config.min_area(class_name, 50),
            self.nms_threshold,
        )
        mapped = []
        for item in items:
            bx1, by1, bx2, by2 = item["bbox"]
            full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
            full_mask[y1:y2, x1:x2] = item["mask"]
            mapped.append(
                {
                    "bbox": (bx1 + x1, by1 + y1, bx2 + x1, by2 + y1),
                    "confidence": item["confidence"],
                    "class_name": item["class_name"],
                    "mask": full_mask,
                    "area": item["area"],
                }
            )
        return mapped

    def make_detection(self, detection_id, item, depth, info_msg, image_header):
        point, depth_valid, method = self.estimate_point(item, depth, info_msg)
        pose = PoseStamped()
        pose.header = Header(stamp=image_header.stamp, frame_id=image_header.frame_id)
        pose.pose.position = point
        pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        size = self.estimate_size(item, point, info_msg)
        pose = self.transform_pose(pose)

        msg = Detection3D()
        msg.header = pose.header
        msg.id = detection_id
        msg.class_name = item["class_name"]
        msg.role = "candidate"
        msg.state = "candidate" if depth_valid else "vision_only"
        msg.confidence = float(item["confidence"])
        x1, y1, x2, y2 = item["bbox"]
        msg.bbox.xmin = int(x1)
        msg.bbox.ymin = int(y1)
        msg.bbox.xmax = int(x2)
        msg.bbox.ymax = int(y2)
        msg.bbox.confidence = float(item["confidence"])
        msg.bbox.class_name = item["class_name"]
        msg.pose = pose
        msg.box.center = pose.pose.position
        msg.box.orientation = pose.pose.orientation
        msg.box.size = size
        msg.box.confidence = float(item["confidence"])
        msg.box.class_name = item["class_name"]
        msg.coordinate_method = method
        msg.depth_valid = bool(depth_valid)
        msg.geometry_constraint_passed = bool(depth_valid)
        msg.history_constraint_passed = True
        return msg

    def estimate_point(self, item, depth, info_msg):
        mask = item["mask"] > 0
        depth_m = self.depth_to_meters(depth)
        valid = mask & np.isfinite(depth_m) & (depth_m > 0.1) & (depth_m < 8.0)
        method = "pointcloud_mask_median"
        if np.count_nonzero(valid) < 8:
            x1, y1, x2, y2 = item["bbox"]
            cx = int((x1 + x2) * 0.5)
            cy = int((y1 + y2) * 0.5)
            radius = 5
            valid = np.zeros_like(mask, dtype=bool)
            valid[max(0, cy - radius) : cy + radius + 1, max(0, cx - radius) : cx + radius + 1] = True
            valid = valid & np.isfinite(depth_m) & (depth_m > 0.1) & (depth_m < 8.0)
            method = "pointcloud_center_window_median"
        if np.count_nonzero(valid) < 3:
            x1, y1, x2, y2 = item["bbox"]
            cx = int((x1 + x2) * 0.5)
            cy = int((y1 + y2) * 0.5)
            return self.project_pixel(cx, cy, 0.0, info_msg), False, "vision_bbox_center"
        ys, xs = np.nonzero(valid)
        z = float(np.median(depth_m[ys, xs]))
        x = int(np.median(xs))
        y = int(np.median(ys))
        return self.project_pixel(x, y, z, info_msg), True, method

    def depth_to_meters(self, depth):
        arr = depth.astype(np.float32)
        if depth.dtype == np.uint16 or np.nanmax(arr) > 20.0:
            arr *= 0.001
        return arr

    def project_pixel(self, x, y, z, info_msg):
        fx = float(info_msg.K[0])
        fy = float(info_msg.K[4])
        cx = float(info_msg.K[2])
        cy = float(info_msg.K[5])
        if z <= 0.0 or fx == 0.0 or fy == 0.0:
            return Point(x=0.0, y=0.0, z=0.0)
        return Point(x=(float(x) - cx) * z / fx, y=(float(y) - cy) * z / fy, z=z)

    def transform_pose(self, pose):
        if not pose.header.frame_id or pose.header.frame_id == self.target_frame:
            pose.header.frame_id = pose.header.frame_id or self.target_frame
            return pose
        try:
            try:
                transform = self.tf_buffer.lookup_transform(
                    self.target_frame,
                    pose.header.frame_id,
                    pose.header.stamp,
                    timeout=rospy.Duration(0.05),
                )
            except tf2_ros.ExtrapolationException:
                transform = self.tf_buffer.lookup_transform(
                    self.target_frame,
                    pose.header.frame_id,
                    rospy.Time(0),
                    timeout=rospy.Duration(0.05),
                )
            translation = transform.transform.translation
            rotation = transform.transform.rotation
            rotated = rotate_vector(
                [pose.pose.position.x, pose.pose.position.y, pose.pose.position.z],
                rotation,
            )
            pose.header = Header(stamp=transform.header.stamp, frame_id=transform.header.frame_id)
            pose.pose.position = Point(
                x=float(rotated[0] + translation.x),
                y=float(rotated[1] + translation.y),
                z=float(rotated[2] + translation.z),
            )
        except Exception as exc:
            rospy.logwarn_throttle(
                5.0,
                "TF transform %s -> %s unavailable, publishing camera-frame candidate: %s",
                pose.header.frame_id,
                self.target_frame,
                exc,
            )
        return pose

    def estimate_size(self, item, point, info_msg):
        x1, y1, x2, y2 = item["bbox"]
        z = max(float(point.z), 0.1)
        fx = max(float(info_msg.K[0]), 1.0)
        fy = max(float(info_msg.K[4]), 1.0)
        width_m = max((float(x2 - x1) * z / fx), 0.03)
        height_m = max((float(y2 - y1) * z / fy), 0.03)
        if item["class_name"] == "aluminum_block":
            return Vector3(x=0.05, y=0.05, z=0.05)
        if item["class_name"] == "chair_seat":
            return Vector3(x=width_m, y=height_m, z=0.04)
        return Vector3(x=width_m, y=height_m, z=0.40)

    def draw(self, image, item, color, label):
        x1, y1, x2, y2 = item["bbox"]
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        text = f"{label} {item['confidence']:.2f}"
        cv2.putText(image, text, (int(x1), max(int(y1) - 5, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def main():
    rospy.init_node("colt_detector")
    DetectorNode()
    rospy.spin()


if __name__ == "__main__":
    main()
