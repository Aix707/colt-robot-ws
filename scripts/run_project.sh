#!/usr/bin/env bash
set -eo pipefail

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-${WS_ROOT}/src/colt/colt_bridle/models/runtime/current}"
FIELD_RUNTIME_PID=""
PERCEPTION_PID=""
UI_PID=""
STARTUP_TIMEOUT_SEC="${STARTUP_TIMEOUT_SEC:-45}"
START_UI="${START_UI:-auto}"

ros_ip_from_route() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -n "${ip}" ]]; then
    echo "${ip}"
    return
  fi
  local target="${SSH_CLIENT%% *}"
  [[ -z "${target}" ]] && target="8.8.8.8"
  ip route get "${target}" 2>/dev/null | awk '{
    for (i = 1; i <= NF; i++) {
      if ($i == "src") { print $(i + 1); exit }
    }
  }'
}

cleanup() {
  if [[ -n "${UI_PID}" ]] && kill -0 "${UI_PID}" >/dev/null 2>&1; then
    kill "${UI_PID}" >/dev/null 2>&1 || true
    wait "${UI_PID}" 2>/dev/null || true
  fi
  if [[ -n "${PERCEPTION_PID}" ]] && kill -0 "${PERCEPTION_PID}" >/dev/null 2>&1; then
    kill "${PERCEPTION_PID}" >/dev/null 2>&1 || true
    wait "${PERCEPTION_PID}" 2>/dev/null || true
  fi
  if [[ -n "${FIELD_RUNTIME_PID}" ]] && kill -0 "${FIELD_RUNTIME_PID}" >/dev/null 2>&1; then
    kill "${FIELD_RUNTIME_PID}" >/dev/null 2>&1 || true
    wait "${FIELD_RUNTIME_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

ensure_running() {
  local pid="$1"
  local label="$2"
  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    echo "${label} exited during startup." >&2
    exit 1
  fi
}

wait_for_topic() {
  local topic="$1"
  local timeout_sec="$2"
  echo "Waiting for ${topic} ..."
  if ! timeout "${timeout_sec}s" rostopic echo -n 1 "${topic}" >/dev/null 2>&1; then
    echo "Timed out waiting for ${topic}" >&2
    exit 1
  fi
}

wait_for_tf() {
  local source_frame="$1"
  local target_frame="$2"
  local timeout_sec="$3"
  local log_file
  local tf_pid
  local deadline
  log_file="$(mktemp /tmp/colt_tf_check_XXXXXX.log)"
  echo "Waiting for TF ${source_frame} -> ${target_frame} ..."
  rosrun tf tf_echo "${source_frame}" "${target_frame}" >"${log_file}" 2>&1 &
  tf_pid=$!
  deadline=$((SECONDS + timeout_sec))
  while (( SECONDS < deadline )); do
    if grep -q "Translation:" "${log_file}"; then
      kill "${tf_pid}" >/dev/null 2>&1 || true
      wait "${tf_pid}" 2>/dev/null || true
      rm -f "${log_file}"
      return 0
    fi
    if ! kill -0 "${tf_pid}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
  echo "Timed out waiting for TF ${source_frame} -> ${target_frame}" >&2
  cat "${log_file}" >&2 || true
  kill "${tf_pid}" >/dev/null 2>&1 || true
  wait "${tf_pid}" 2>/dev/null || true
  rm -f "${log_file}"
  exit 1
}

check_runtime() {
  echo "Checking Python dependencies and runtime models..."
  python3 "${WS_ROOT}/src/colt/colt_bridle/scripts/detector_node.py" --check "${RUNTIME_DIR}"
}

should_start_ui() {
  if [[ "${START_UI}" == "true" ]]; then
    return 0
  fi
  if [[ "${START_UI}" == "false" ]]; then
    return 1
  fi
  [[ -n "${DISPLAY:-}" ]]
}

if [[ ! -f "${WS_ROOT}/devel/setup.bash" ]]; then
  echo "Building workspace..."
  (
    cd "${WS_ROOT}"
    catkin_make
  )
fi

source /opt/ros/noetic/setup.bash
source "${WS_ROOT}/devel/setup.bash"
set -u
export PYTHONNOUSERSITE=1

if [[ -z "${ROS_IP:-}" ]]; then
  ROS_IP="$(ros_ip_from_route)"
  export ROS_IP
fi
if [[ -n "${ROS_IP:-}" ]]; then
  export ROS_MASTER_URI="http://${ROS_IP}:11311"
  echo "ROS network: ROS_IP=${ROS_IP} ROS_MASTER_URI=${ROS_MASTER_URI}"
fi

echo "Starting camera, pan-tilt driver, robot TF, and odometry..."
roslaunch colt_bridle field_runtime.launch &
FIELD_RUNTIME_PID=$!

sleep 5
ensure_running "${FIELD_RUNTIME_PID}" "field_runtime.launch"
wait_for_topic "/kinect2/qhd/image_color_rect" "${STARTUP_TIMEOUT_SEC}"
wait_for_topic "/kinect2/qhd/image_depth_rect" "${STARTUP_TIMEOUT_SEC}"
wait_for_topic "/kinect2/qhd/camera_info" "${STARTUP_TIMEOUT_SEC}"
wait_for_topic "/joint_states" "${STARTUP_TIMEOUT_SEC}"
wait_for_tf "map" "body_link" "${STARTUP_TIMEOUT_SEC}"

check_runtime

echo "Starting perception and pan-tilt control..."
roslaunch colt_bridle online_perception.launch \
  runtime_dir:="${RUNTIME_DIR}" \
  start_pt_control:=true &
PERCEPTION_PID=$!

sleep 3
ensure_running "${PERCEPTION_PID}" "online_perception.launch"

if should_start_ui; then
  echo "Starting OpenCV chair selector..."
  roslaunch colt_ui cv_selector.launch &
  UI_PID=$!
  wait "${UI_PID}"
else
  echo "Skipping OpenCV selector because DISPLAY is not set. Set START_UI=true to force it."
  echo "Perception and pan-tilt control are running; press Ctrl+C to stop."
  wait "${PERCEPTION_PID}"
fi
