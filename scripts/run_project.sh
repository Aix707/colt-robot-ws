#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${WS_ROOT}/.venv-py311/bin/python"
RUNTIME_DIR="${RUNTIME_DIR:-${WS_ROOT}/src/colt/colt_bridle/models/runtime/current}"
PYTHONPATH_VALUE="${WS_ROOT}/devel/lib/python3/dist-packages:/opt/ros/noetic/lib/python3/dist-packages:${PYTHONPATH:-}"
PERCEPTION_PID=""
MARKER_PID=""

cleanup() {
  if [[ -n "${PERCEPTION_PID}" ]] && kill -0 "${PERCEPTION_PID}" >/dev/null 2>&1; then
    kill "${PERCEPTION_PID}" >/dev/null 2>&1 || true
    wait "${PERCEPTION_PID}" 2>/dev/null || true
  fi
  if [[ -n "${MARKER_PID}" ]] && kill -0 "${MARKER_PID}" >/dev/null 2>&1; then
    kill "${MARKER_PID}" >/dev/null 2>&1 || true
    wait "${MARKER_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Missing ${VENV_PY}" >&2
  echo "Run scripts/install_runtime.sh first." >&2
  exit 1
fi

if [[ ! -f "${WS_ROOT}/devel/setup.bash" ]]; then
  echo "Building workspace..."
  (
    cd "${WS_ROOT}"
    catkin_make
  )
fi

source /opt/ros/noetic/setup.bash
source "${WS_ROOT}/devel/setup.bash"

echo "Checking runtime package..."
PYTHONPATH="${PYTHONPATH_VALUE}" \
  "${VENV_PY}" "${WS_ROOT}/src/colt/colt_bridle/scripts/detector_node.py" \
  --check "${RUNTIME_DIR}"

echo "Starting perception and pan-tilt control..."
roslaunch colt_bridle online_perception.launch \
  runtime_dir:="${RUNTIME_DIR}" \
  python_launch_prefix:="${VENV_PY}" \
  start_pt_control:=true &
PERCEPTION_PID=$!

sleep 3

echo "Starting RViz marker publisher..."
rosrun colt_ui rviz_marker_publisher.py &
MARKER_PID=$!

echo "Starting terminal UI..."
echo "Choose source chair with: s <number>"
echo "Choose target chair with: t <number>"
echo "Switch pan-tilt to target chair with: swap"
echo "RViz markers: /colt/ui/rviz_markers"
roslaunch colt_ui terminal_selector.launch
