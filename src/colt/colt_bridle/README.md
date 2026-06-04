# colt_bridle

`colt_bridle` 当前只保留三项功能：

1. 最小采集
2. 实时检测
3. 二轴云台控制

## 直接入口

```text
capture_session.launch
external_nodes.launch
field_runtime.launch
online_perception.launch
pt_control.launch
```

## 外部依赖节点

```bash
source devel/setup.bash
roslaunch colt_bridle external_nodes.launch
```

该入口只启动 Colt/Paddock 包本身以外的节点：Kinect2、`wpv4_pt` 云台驱动、`wpv4_core` 底盘里程计、机器人模型 TF 和默认 `map -> odom` 静态 TF。
如果现场已经有定位系统发布真实 `map -> odom`，启动时传 `start_map_odom_tf:=false`。

`field_runtime.launch` 保留为兼容入口，内部只 include `external_nodes.launch`。

可选开关：

```text
start_base:=true
start_camera:=true
start_pt_driver:=true
start_robot_tf:=true
start_map_odom_tf:=true
base_serial_port:=/dev/wpv4_base
pt_serial_port:=/dev/wpv4_pt
```

与其他项目合并运行时，只启动对方项目没有提供的外部节点，避免重复发布 `/joint_states`、相机话题、云台驱动或 `map -> odom`。

## 采集

```bash
source devel/setup.bash
roslaunch colt_bridle capture_session.launch
```

采集只保存 RGB、depth、camera_info、TF、joint states，不发控制命令。

## 检测

runtime 检查：

```bash
source devel/setup.bash
PYTHONNOUSERSITE=1 python3 src/colt/colt_bridle/scripts/detector_node.py \
  --check src/colt/colt_bridle/models/runtime/current
```

启动：

```bash
source devel/setup.bash
roslaunch colt_bridle online_perception.launch \
  runtime_dir:=$PWD/src/colt/colt_bridle/models/runtime/current
```

输出：

```text
/colt/bridle/detections
/colt/bridle/debug_image
```

对象规则：

- `chair`：维护当前运行内稳定 `id`
- `seat`：仅对 `source / target` 椅子维护
- `item`：仅对 `source` 椅面维护
- `frame_id` 默认输出 `map`
- `state=0/2` 的对象坐标会跟随当前 `state=1` 锚点对象实时纠正

稳定 `chair` 依赖：

```text
map <- body_link <- camera
```

离线 bag 没有 TF 时，用相机坐标系测试：

终端 1：

```bash
source devel/setup.bash
roslaunch colt_bridle online_perception.launch \
  target_frame:=kinect2_rgb_optical_frame \
  robot_frame:=kinect2_rgb_optical_frame
```

终端 2：

```bash
source devel/setup.bash
roslaunch colt_ui cv_selector.launch
```

终端 3：

```bash
source devel/setup.bash
rosbag play /home/xia/桌面/colt_capture.bag --clock
```

## 云台控制

单独启动：

```bash
source devel/setup.bash
roslaunch colt_bridle pt_control.launch
```

或跟检测一起启动：

```bash
source devel/setup.bash
roslaunch colt_bridle online_perception.launch \
  runtime_dir:=$PWD/src/colt/colt_bridle/models/runtime/current \
  start_pt_control:=true
```

输入：

```text
/colt/bridle/detections
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
/colt/ui/pt_state
/joint_states
```

输出：

```text
/wpv4_pt/joint_ctrl_degree
```

控制规则：

- `pt_state=0`：朝向源椅
- `pt_state=1`：朝向目标椅
- 当前 `pt_state` 指向的椅子已选择且可见时，云台追踪该椅子
- 追踪不要求椅子在画面中心；只要当前追踪椅子不是 `state=lost`，就会按 bbox 中心误差向画面中心靠近
- 当前追踪椅子未选择或检测超过 `detection_timeout_sec` 时，`wp_tilt` 在限位内左右扫视，`wp_pitch` 固定向前
- 当前追踪椅子 `state=lost` 后，先保持最后角度，再做局部找回；超时后回到左右全局扫视
- 追踪时默认按 x/y 误差修正 `wp_tilt/wp_pitch`，让目标靠近画面中心

## 边界

- 不发布 `/cmd_vel`
- 不控制机械臂
- `external_nodes.launch` 只负责实测需要的基础设备和 TF，不启动底盘运动命令、机械臂或抓取链路
- 更多训练边界只保留 `docs/04_model_training_boundary.md`
