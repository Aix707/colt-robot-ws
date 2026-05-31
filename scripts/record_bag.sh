#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DURATION="${1:-20}"
OUTPUT="${2:-/home/xia/桌面/colt_capture.bag}"

source /opt/ros/noetic/setup.bash
source "${WS_ROOT}/devel/setup.bash"

cleanup() {
  pkill -f "rosbag record.*colt_capture" 2>/dev/null || true
  pkill -f "image_view.*kinect2" 2>/dev/null || true
}
trap cleanup EXIT

# 启动相机（如果没在跑）
if ! rostopic info /kinect2/qhd/image_color_rect >/dev/null 2>&1; then
  echo "Starting kinect2_bridge ..."
  roslaunch kinect2_bridge kinect2_bridge.launch \
    depth_method:=cpu reg_method:=cpu &
  sleep 8
fi

if [[ -n "${DISPLAY:-}" ]]; then
  echo "Opening camera view ..."
  rosrun image_view image_view image:=/kinect2/qhd/image_color_rect &
fi

echo "Recording ${DURATION}s -> ${OUTPUT} ..."
rosbag record -O "${OUTPUT}" --duration="${DURATION}" \
  /kinect2/qhd/image_color_rect \
  /kinect2/qhd/image_depth_rect \
  /kinect2/qhd/camera_info \
  /joint_states \
  /tf \
  /tf_static

echo "Done: ${OUTPUT} ($(du -h "${OUTPUT}" | cut -f1))"
