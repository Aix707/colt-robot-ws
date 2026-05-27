# colt_bridle

`colt_bridle` 现在只保留三项功能：

1. 采集
2. 实时检测
3. 二轴云台控制

## 直接入口

```text
capture_session.launch
online_perception.launch
pt_control.launch
```

## 采集

```bash
source devel/setup.bash
roslaunch colt_bridle capture_session.launch
```

采集只保存 RGB、depth、points、camera_info、TF、joint states，不发控制命令。

## 检测

runtime 检查：

```bash
PYTHONPATH=$PWD/devel/lib/python3/dist-packages:/opt/ros/noetic/lib/python3/dist-packages \
  .venv-py311/bin/python src/colt/colt_bridle/scripts/detector_node.py \
  --check src/colt/colt_bridle/models/runtime/current
```

启动：

```bash
source devel/setup.bash
roslaunch colt_bridle online_perception.launch \
  runtime_dir:=$PWD/src/colt/colt_bridle/models/runtime/current \
  python_launch_prefix:=$PWD/.venv-py311/bin/python
```

输出：

```text
/colt/bridle/detections
/colt/bridle/debug_image
```

对象规则：

- `chair`：维护稳定世界系 `id`
- `seat`：仅对 `source / target` 椅子维护
- `item`：仅对 `source` 椅面维护
- `frame_id` 默认输出 `map`
- `state=0/2` 的对象坐标会跟随当前 `state=1` 锚点对象实时纠正

稳定 `chair` 依赖：

```text
map <- body_link <- camera
```

## 云台控制

单独启动：

```bash
source devel/setup.bash
roslaunch colt_bridle pt_control.launch \
  python_launch_prefix:=$PWD/.venv-py311/bin/python
```

或跟检测一起启动：

```bash
source devel/setup.bash
roslaunch colt_bridle online_perception.launch \
  runtime_dir:=$PWD/src/colt/colt_bridle/models/runtime/current \
  python_launch_prefix:=$PWD/.venv-py311/bin/python \
  start_pt_control:=true
```

输入：

```text
/colt/bridle/detections
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
/colt/ui/pt_state
/wpv4_pt/raw_joint_states
```

输出：

```text
/wpv4_pt/joint_ctrl_degree
```

控制规则：

- `pt_state=0`：朝向源椅
- `pt_state=1`：朝向目标椅
- 源椅和目标椅未同时指定完时，在限位内扫视
- 源椅和目标椅都指定完后，默认先朝向源椅
- 水平限位 `-20` 到 `20` 度
- 俯仰限位 `-20` 到 `0` 度
- 控制逻辑只做简单小步调整

## 边界

- 不发布 `/cmd_vel`
- 不控制机械臂
- 不在包内代启 Kinect2、云台驱动或 `robot_state_publisher`
- 更多训练边界只保留 `docs/04_model_training_boundary.md`
