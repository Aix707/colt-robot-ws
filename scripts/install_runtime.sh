#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${WS_ROOT}/src/colt/colt_bridle/models/runtime/current}"

set +u
source /opt/ros/noetic/setup.bash
if [[ -f "${WS_ROOT}/devel/setup.bash" ]]; then
  source "${WS_ROOT}/devel/setup.bash"
fi
set -u

export PYTHONNOUSERSITE=1

python3 - "${RUNTIME_DIR}" <<'PY'
import importlib
import json
import sys
from pathlib import Path

runtime_dir = Path(sys.argv[1]).expanduser().resolve()
modules = [
    ("rospy", "rospy"),
    ("cv2", "cv2"),
    ("torch", "torch"),
    ("torchvision", "torchvision"),
    ("ultralytics", "ultralytics"),
    ("onnxruntime", "onnxruntime"),
    ("numpy", "numpy"),
    ("yaml", "pyyaml"),
    ("rospkg", "rospkg"),
    ("catkin_pkg", "catkin_pkg"),
]
missing = []
versions = {}
for module_name, package_name in modules:
    try:
        module = importlib.import_module(module_name)
        versions[module_name] = getattr(module, "__version__", "ok")
    except Exception as exc:
        missing.append(f"{package_name}: {exc}")

required_files = [
    "release_manifest.json",
    "preprocess.yaml",
    "thresholds.yaml",
    "roi_rules.yaml",
    "chair_seg.onnx",
    "chair_seat_roi_seg.onnx",
    "aluminum_roi_seg.onnx",
]
missing_files = [name for name in required_files if not (runtime_dir / name).is_file()]

onnx_errors = []
if not missing and not missing_files:
    import onnxruntime as ort

    for name in ("chair_seg.onnx", "chair_seat_roi_seg.onnx", "aluminum_roi_seg.onnx"):
        try:
            ort.InferenceSession(str(runtime_dir / name), providers=["CPUExecutionProvider"])
        except Exception as exc:
            onnx_errors.append(f"{name}: {exc}")

result = {
    "python": sys.version.split()[0],
    "runtime_dir": str(runtime_dir),
    "versions": versions,
    "missing_python_packages": missing,
    "missing_runtime_files": missing_files,
    "onnx_errors": onnx_errors,
    "ready": not missing and not missing_files and not onnx_errors,
}
print(json.dumps(result, ensure_ascii=False, indent=2))

if result["ready"]:
    raise SystemExit(0)

print("\nInstall missing system dependencies manually, for example:", file=sys.stderr)
print("  sudo apt-get update", file=sys.stderr)
print("  sudo apt-get install -y python3-pip python3-opencv libgl1 libglib2.0-0", file=sys.stderr)
print("  sudo -H python3 -m pip install -U 'pip<25' setuptools wheel", file=sys.stderr)
print("  sudo -H python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \\", file=sys.stderr)
print("    --extra-index-url https://download.pytorch.org/whl/cpu \\", file=sys.stderr)
print("    'numpy==1.24.4' 'torch==2.4.1+cpu' 'torchvision==0.19.1+cpu' \\", file=sys.stderr)
print("    'opencv-python==4.10.0.84' 'onnx==1.17.0' 'onnxruntime==1.17.3' \\", file=sys.stderr)
print("    'ultralytics==8.4.56' pyyaml rospkg catkin_pkg", file=sys.stderr)
raise SystemExit(2)
PY
