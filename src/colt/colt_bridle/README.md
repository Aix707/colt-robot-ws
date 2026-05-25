# colt_bridle

`colt_bridle` 是 Colt 的实机运行包。它负责相机/云台相关的采集、模型运行入口、场景融合、RViz 输出和云台观察目标规划。

实测阶段使用真实 Kinect2、真实云台状态和训练得到的 v001 runtime 三模型包。

## 已有入口

### 硬件基础链路

```bash
cd ~/colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_hardware.launch
```

启动 Kinect2、`wpv4_pt` 云台状态、`joint_state_publisher` 和 `robot_state_publisher`。

2026-05-22 实测时，现场已有旧导航/建图链路在运行，不能再叠加启动完整
`field_hardware.launch`。当只需要采集界面时，已验证的旁路启动方式是只启动 Kinect2：

```bash
screen -L -Logfile /tmp/colt_kinect.log -dmS colt_kinect \
  bash -lc 'cd /home/robot/colt-robot-ws; source devel/setup.bash; roslaunch kinect2_bridge kinect2_bridge.launch'
```

### 采集 session

```bash
cd ~/colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_capture_session.launch
```

实测机本地桌面窗口使用：

```bash
export DISPLAY=:1
export XAUTHORITY=/run/user/1000/gdm/Xauthority
```

推荐用 `screen` 启动，避免 SSH 断开时关闭采集面板：

```bash
screen -L -Logfile /tmp/colt_capture.log -dmS colt_capture \
  bash -lc 'cd /home/robot/colt-robot-ws; source devel/setup.bash; export DISPLAY=:1; export XAUTHORITY=/run/user/1000/gdm/Xauthority; roslaunch colt_bridle field_capture_session.launch output_root:=/home/robot/colt-robot-ws/data/capture_sessions'
```

默认订阅：

```text
/kinect2/qhd/image_color_rect
/kinect2/qhd/image_depth_rect
/kinect2/qhd/points
/kinect2/qhd/camera_info
/tf
/tf_static
/joint_states
/wpv4_pt/raw_joint_states
```

默认输出：

```text
/home/robot/colt-robot-ws/data/capture_sessions/
```

按键：

```text
s start/resume
p pause
q finish
f far_chair
c near_chair_aluminum
a aluminum_present
n aluminum_absent
m motion_base
o arm_occlusion
```

检查当前 session：

```bash
screen -ls
screen -r colt_capture
tail -n 50 /tmp/colt_capture.log
```

传回开发机：

```bash
cd /home/xia/桌面/catkin_ws
mkdir -p src/colt/colt_trainer/datasets/raw
rsync -av --partial --progress \
  robot@10.169.113.176:/home/robot/colt-robot-ws/data/capture_sessions/session_YYYYMMDD_HHMMSS/ \
  src/colt/colt_trainer/datasets/raw/session_YYYYMMDD_HHMMSS/
```

第一次正式采集结果：

```text
session: session_20260522_142754
frames: 215
local copy: src/colt/colt_trainer/datasets/raw/session_20260522_142754/
```

### runtime 包检查

```bash
python3 src/colt/colt_bridle/scripts/runtime_package_loader.py --check src/colt/colt_bridle/models/runtime/v001
```

从 Windows 训练机拷回导出目录后，也可以在工作空间根目录执行：

```bash
./scripts/install_runtime.sh /path/to/exports/colt_runtime_v001/runtime v001
```

ROS 状态发布：

```bash
source devel/setup.bash
roslaunch colt_bridle runtime_package_loader.launch runtime_dir:=/home/robot/colt-robot-ws/src/colt/colt_bridle/models/runtime/v001
```

### 在线感知链路

v001 runtime 是三模型 ONNX 包：

```text
chair_seg.onnx
chair_seat_roi_seg.onnx
aluminum_roi_seg.onnx
```

这些 ONNX 需要新版 ONNXRuntime。实测机建议用 Python 3.11 venv 运行 detector，ROS Noetic
系统 Python 仍用于 `catkin_make`、采集脚本和常规 ROS 工具。

首次准备：

```bash
cd ~/colt-robot-ws
python3.11 -m venv .venv-py311
.venv-py311/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --upgrade pip onnxruntime opencv-python-headless numpy pyyaml rospkg catkin_pkg
```

预检：

```bash
cd ~/colt-robot-ws
source devel/setup.bash
PYTHONPATH=$PWD/devel/lib/python3/dist-packages:/opt/ros/noetic/lib/python3/dist-packages \
  .venv-py311/bin/python src/colt/colt_bridle/scripts/check_online_perception.py \
  src/colt/colt_bridle/models/runtime/v001
```

通过标准是输出 JSON 中 `"ready": true`，且三份 ONNX 都能创建 `InferenceSession`。

只启动在线感知，不启动硬件：

```bash
cd ~/colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle online_perception.launch \
  runtime_dir:=$PWD/src/colt/colt_bridle/models/runtime/v001 \
  detector_launch_prefix:=$PWD/.venv-py311/bin/python \
  start_hardware:=false
```

输出：

```text
/colt/bridle/candidates
/colt/bridle/detections
/colt/bridle/markers
/colt/bridle/debug_image
/colt/bridle/runtime_status
/colt/bridle/perception_state
```

检查：

```bash
rostopic hz /colt/bridle/candidates
rostopic echo -n 1 /colt/bridle/perception_state
rostopic hz /colt/bridle/markers
```

安全边界：

- `online_perception.launch` 默认 `start_hardware:=false`。
- detector、融合和 RViz 节点只发布感知、状态和 marker，不发布底盘、云台或机械臂运动命令。
- 第一次实测只做静态识别、坐标和 RViz 检查。

## 保留节点

```text
colt_capture_session.py      # 实测数据采集
runtime_package_loader.py    # runtime 包检查
check_online_perception.py   # 在线感知 Python/ONNX/runtime 预检
detector_node.py             # v001 三阶段 ROI 真实模型推理，发布 /colt/bridle/candidates
scene_fusion_node.py         # detector 输出后的源/目标椅和小铝块融合
rviz_visualizer_node.py      # Detection3DArray -> MarkerArray
pt_view_planner_node.py      # 输出 /colt/bridle/pt_view_goal
```

## 后续需要新增

```text
pt_limited_forwarder_node.py # 云台限幅转发，第一版限制在零位附近 ±15°
```
