#!/usr/bin/env python3
"""Preflight checks for Colt online perception before a field run."""

import argparse
import importlib
import json

from runtime_package_loader import validate_runtime_package


def check_module(name):
    try:
        importlib.import_module(name)
        return {"available": True, "error": ""}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def check_onnxruntime(runtime_status, module_status):
    result = {
        "available": module_status.get("onnxruntime", {}).get("available", False),
        "models": {},
        "errors": [],
    }
    if not result["available"]:
        error = module_status.get("onnxruntime", {}).get("error", "")
        result["errors"].append(error or "onnxruntime is not installed")
        return result

    import onnxruntime as ort

    for model_file, model_path in runtime_status.get("onnx_models", {}).items():
        try:
            session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            result["models"][model_file] = {
                "input": session.get_inputs()[0].name,
                "outputs": [item.name for item in session.get_outputs()],
            }
        except Exception as exc:
            result["errors"].append(f"{model_file}: {exc}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime_dir", help="Runtime package directory to check.")
    parser.add_argument("--allow-missing-onnx", action="store_true")
    args = parser.parse_args()

    runtime_status = validate_runtime_package(
        args.runtime_dir,
        require_onnx=not args.allow_missing_onnx,
    )
    result = {
        "runtime": runtime_status,
        "python_modules": {},
        "onnxruntime": {},
        "ready": False,
    }
    result["python_modules"] = {
        name: check_module(name)
        for name in ("rospy", "message_filters", "tf2_ros", "cv2", "numpy", "onnxruntime")
    }
    result["onnxruntime"] = check_onnxruntime(runtime_status, result["python_modules"])

    missing_modules = [
        name for name, status in result["python_modules"].items()
        if name != "onnxruntime" and not status["available"]
    ]
    result["ready"] = (
        runtime_status.get("ready", False)
        and not missing_modules
        and result["onnxruntime"].get("available", False)
        and not result["onnxruntime"].get("errors")
    )
    result["missing_modules"] = missing_modules
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ready"] else 2)


if __name__ == "__main__":
    main()
