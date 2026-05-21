# colt_bridle

`colt_bridle` 是 Colt 的实机运行包。它负责相机/云台相关的采集、模型运行入口、场景融合、RViz 输出和云台观察目标规划。

实测阶段使用真实 Kinect2、真实云台状态和训练得到的 v002 runtime 包。

## 已有入口

### 硬件基础链路

```bash
cd /colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_hardware.launch
```

启动 Kinect2、`wpv4_pt` 云台状态、`joint_state_publisher` 和 `robot_state_publisher`。

### 采集 session

```bash
cd /colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_capture_session.launch
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
/colt-robot-ws/data/capture_sessions/
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

### runtime 包检查

```bash
python3 src/colt/colt_bridle/scripts/runtime_package_loader.py --check src/colt/colt_bridle/models/runtime/v002
```

从 Windows 训练机拷回导出目录后，也可以在工作空间根目录执行：

```bash
./scripts/install_runtime.sh /path/to/exports/colt_runtime_v002/runtime v002
```

ROS 状态发布：

```bash
source devel/setup.bash
roslaunch colt_bridle runtime_package_loader.launch runtime_dir:=/colt-robot-ws/src/colt/colt_bridle/models/runtime/v002
```

## 保留节点

```text
colt_capture_session.py      # 实测数据采集
runtime_package_loader.py    # v002 runtime 包检查
scene_fusion_node.py         # 后续 detector 输出后的源/目标椅和小铝块融合
rviz_visualizer_node.py      # Detection3DArray -> MarkerArray
pt_view_planner_node.py      # 输出 /colt/bridle/pt_view_goal
```

## 后续需要新增

```text
detector_node.py             # 真实模型推理，发布 /colt/bridle/candidates
online_perception.launch     # 实测在线一键启动
pt_limited_forwarder_node.py # 云台限幅转发，第一版限制在零位附近 ±15°
```
