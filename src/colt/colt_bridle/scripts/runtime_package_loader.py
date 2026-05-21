#!/usr/bin/env python3
"""Validate Colt runtime model packages and publish their readiness state."""

import argparse
import json
from pathlib import Path

import yaml

try:
    import rospy
    from colt_msgs.msg import PerceptionState
    from std_msgs.msg import Header, String
except ImportError:  # Allows --check to run before sourcing a ROS environment.
    rospy = None
    Header = None
    PerceptionState = None
    String = None


EXPECTED_CLASSES = ["chair", "chair_seat", "aluminum_block"]
EXPECTED_ONNX_FILES = ["chair_seat_seg.onnx", "aluminum_roi_seg.onnx"]
REQUIRED_FILES = [
    "labels.yaml",
    "preprocess.yaml",
    "thresholds.yaml",
    "roi_rules.yaml",
    "release_manifest.json",
]


def load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_classes(classes):
    if isinstance(classes, dict):
        return {int(key): str(value) for key, value in classes.items()}
    if isinstance(classes, list):
        return {index: str(value) for index, value in enumerate(classes)}
    return {}


def extract_classes(labels):
    classes = normalize_classes(labels.get("classes", {}))
    if classes:
        return classes

    merged = {}
    next_index = 0
    for model_data in labels.get("models", {}).values():
        for class_name in normalize_classes(model_data.get("classes", {})).values():
            if class_name not in merged.values():
                merged[next_index] = class_name
                next_index += 1
    return merged


def expected_model_files(manifest, fallback):
    models = manifest.get("models", {})
    if isinstance(models, dict):
        files = [
            str(model.get("file", ""))
            for model in models.values()
            if isinstance(model, dict) and model.get("file")
        ]
        if files:
            return files
    if isinstance(models, list):
        files = [
            str(model.get("file", ""))
            for model in models
            if isinstance(model, dict) and model.get("file")
        ]
        if files:
            return files
    model_name = manifest.get("model_name", "")
    if model_name:
        return [f"{model_name}.onnx"]
    return list(fallback)


def preprocess_has_input_size(preprocess):
    if preprocess.get("input_size") is not None:
        return True
    models = preprocess.get("models", {})
    if isinstance(models, dict):
        return all(
            isinstance(model, dict) and model.get("input_size") is not None
            for model in models.values()
        )
    return False


def validate_runtime_package(
    runtime_dir,
    expected_classes=None,
    expected_onnx_files=None,
    require_onnx=True,
):
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    expected_classes = expected_classes or EXPECTED_CLASSES
    expected_onnx_files = expected_onnx_files or EXPECTED_ONNX_FILES
    result = {
        "runtime_dir": runtime_dir.as_posix(),
        "ready": False,
        "state": "runtime_blocked",
        "errors": [],
        "warnings": [],
        "files": {},
        "classes": {},
        "manifest": {},
        "preprocess": {},
        "thresholds": {},
        "roi_rules": {},
        "onnx": "",
        "onnx_models": {},
    }

    if not runtime_dir.exists():
        result["errors"].append(f"runtime_dir missing: {runtime_dir.as_posix()}")
        return result

    for name in REQUIRED_FILES:
        path = runtime_dir / name
        result["files"][name] = path.as_posix() if path.exists() else ""
        if not path.exists():
            result["errors"].append(f"missing required file: {name}")

    labels = {}
    manifest = {}
    preprocess = {}
    thresholds = {}
    roi_rules = {}
    try:
        if (runtime_dir / "labels.yaml").exists():
            labels = load_yaml(runtime_dir / "labels.yaml")
    except Exception as exc:
        result["errors"].append(f"failed to read labels.yaml: {exc}")
    try:
        if (runtime_dir / "preprocess.yaml").exists():
            preprocess = load_yaml(runtime_dir / "preprocess.yaml")
    except Exception as exc:
        result["errors"].append(f"failed to read preprocess.yaml: {exc}")
    try:
        if (runtime_dir / "thresholds.yaml").exists():
            thresholds = load_yaml(runtime_dir / "thresholds.yaml")
    except Exception as exc:
        result["errors"].append(f"failed to read thresholds.yaml: {exc}")
    try:
        if (runtime_dir / "roi_rules.yaml").exists():
            roi_rules = load_yaml(runtime_dir / "roi_rules.yaml")
    except Exception as exc:
        result["errors"].append(f"failed to read roi_rules.yaml: {exc}")
    try:
        if (runtime_dir / "release_manifest.json").exists():
            manifest = load_json(runtime_dir / "release_manifest.json")
    except Exception as exc:
        result["errors"].append(f"failed to read release_manifest.json: {exc}")

    classes = extract_classes(labels)
    result["classes"] = classes
    result["manifest"] = manifest
    result["preprocess"] = preprocess
    result["thresholds"] = thresholds
    result["roi_rules"] = roi_rules

    class_names = set(classes.values())
    for class_name in expected_classes:
        if class_name not in class_names:
            result["errors"].append(f"missing expected class: {class_name}")

    if not preprocess_has_input_size(preprocess):
        result["errors"].append("preprocess.yaml missing input_size")
    if "aluminum_block" not in thresholds:
        result["errors"].append("thresholds.yaml missing aluminum_block thresholds")
    if "chair_seat" not in thresholds:
        result["errors"].append("thresholds.yaml missing chair_seat thresholds")
    if not roi_rules:
        result["errors"].append("roi_rules.yaml is empty")

    model_files = expected_model_files(manifest, expected_onnx_files)
    for model_file in model_files:
        onnx_path = runtime_dir / model_file
        if onnx_path.exists():
            result["onnx_models"][model_file] = onnx_path.as_posix()
            if not result["onnx"]:
                result["onnx"] = onnx_path.as_posix()
        elif require_onnx:
            result["errors"].append(f"missing ONNX model file: {model_file}")
        else:
            result["warnings"].append(f"ONNX model file not present: {model_file}")

    if not result["errors"]:
        result["ready"] = True
        result["state"] = "runtime_ready"
    return result


class RuntimePackageNode:
    def __init__(self):
        if rospy is None:
            raise RuntimeError("rospy is not available; use --check outside ROS")
        self.runtime_dir = Path(rospy.get_param("~runtime_dir", "models/runtime/current"))
        self.rate_hz = float(rospy.get_param("~rate", 1.0))
        self.require_onnx = bool(rospy.get_param("~require_onnx", True))
        self.expected_classes = rospy.get_param("~expected_classes", EXPECTED_CLASSES)
        self.expected_onnx_files = rospy.get_param("~expected_onnx_files", EXPECTED_ONNX_FILES)
        self.active_task = rospy.get_param("~active_task", "runtime_package_check")
        self.state_pub = rospy.Publisher(
            "/colt/bridle/perception_state", PerceptionState, queue_size=10, latch=True
        )
        self.status_pub = rospy.Publisher(
            "/colt/bridle/runtime_status", String, queue_size=10, latch=True
        )

    def make_state(self, status):
        msg = PerceptionState()
        msg.header = Header(stamp=rospy.Time.now(), frame_id="base_footprint")
        msg.state = status["state"]
        msg.active_task = self.active_task
        detail = {
            "runtime_dir": status["runtime_dir"],
            "errors": status["errors"],
            "warnings": status["warnings"],
            "onnx_models": status["onnx_models"],
            "classes": list(status["classes"].values()),
        }
        msg.detail = json.dumps(detail, ensure_ascii=True)
        msg.ready_for_navigation = False
        msg.ready_for_grasp = False
        msg.ready_for_place = False
        return msg

    def spin(self):
        rate = rospy.Rate(self.rate_hz)
        while not rospy.is_shutdown():
            status = validate_runtime_package(
                self.runtime_dir,
                expected_classes=self.expected_classes,
                expected_onnx_files=self.expected_onnx_files,
                require_onnx=self.require_onnx,
            )
            self.status_pub.publish(String(data=json.dumps(status, ensure_ascii=True)))
            self.state_pub.publish(self.make_state(status))
            if status["ready"]:
                rospy.loginfo_throttle(30.0, "Colt runtime package ready: %s", status["runtime_dir"])
            else:
                rospy.logwarn_throttle(
                    10.0,
                    "Colt runtime package blocked: %s",
                    "; ".join(status["errors"]) or "unknown error",
                )
            rate.sleep()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", default="", help="Validate a runtime package and print JSON.")
    parser.add_argument("--allow-missing-onnx", action="store_true")
    args, _ = parser.parse_known_args()
    if args.check:
        status = validate_runtime_package(
            args.check,
            expected_classes=EXPECTED_CLASSES,
            expected_onnx_files=EXPECTED_ONNX_FILES,
            require_onnx=not args.allow_missing_onnx,
        )
        print(json.dumps(status, ensure_ascii=False, indent=2))
        raise SystemExit(0 if status["ready"] else 2)

    if rospy is None:
        raise RuntimeError("rospy is required when not using --check")
    rospy.init_node("colt_runtime_package_loader")
    RuntimePackageNode().spin()


if __name__ == "__main__":
    main()
