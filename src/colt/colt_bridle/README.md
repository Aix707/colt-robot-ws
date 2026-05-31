# colt_bridle

`colt_bridle` 当前只保留三项功能：

1. 最小采集
2. 实时检测
3. 二轴云台控制

## 直接入口

```text
capture_session.launch
field_runtime.launch
online_perception.launch
pt_control.launch
```

## 采集

```bash
source devel/setup.bash
roslaunch colt_bridle capture_session.launch
```

采集只保存 RGB、depth、camera_info、TF、joint states，不发控制命令。

## 现场基础链路

```bash
source devel/setup.bash
roslaunch colt_bridle field_runtime.launch
```

该入口启动 Kinect2、`wpv4_pt` 云台驱动、`wpv4_core` 底盘里程计、机器人模型 TF 和默认 `map -> odom` 静态 TF。
如果现场已经有定位系统发布真实 `map -> odom`，启动时传 `start_map_odom_tf:=false`。

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
- 源椅和目标椅未同时指定完时，`wp_tilt` 在限位内左右扫视
- `wp_pitch` 默认固定向前，只有设置 `track_pitch:=true` 才按 y 误差小幅修正
- 源椅和目标椅都指定完后，默认先朝向源椅

## 边界

- 不发布 `/cmd_vel`
- 不控制机械臂
- `field_runtime.launch` 只负责实测需要的基础设备和 TF，不启动底盘运动命令、机械臂或抓取链路
- 更多训练边界只保留 `docs/04_model_training_boundary.md`
