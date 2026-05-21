# colt_bridle 开发文档

`colt_bridle` 是 Colt 系统的感知与安全接口层。名字中的 bridle 表示“缰绳”：它不直接替代底层驱动，而是在 Kinect2、云台、后续小车、机械臂和 UI 之间提供清晰、受约束、可调试的中间层。

当前目录已经是 catkin 运行包。现阶段包含假场景发布、独立采集脚本和运行时模型包检查节点；这些节点都保持旁路边界，不控制云台、不发布底盘或机械臂命令。

## 职责

- 订阅 Kinect2 RGB、深度、彩色点云和 TF。
- 检测椅子、估计椅面、识别小铝块。
- 用深度/点云验证 RGB 检测结果。
- 把小铝块坐标约束到椅面局部坐标系内。
- 对坐标做历史滤波、跳变拒绝和任务状态管理。
- 发布给 RViz、导航、机械臂和 UI 使用的稳定结果。
- 规划云台观察目标，但真实云台命令必须经过安全转发器。

## 不负责

- 不训练模型。
- 不直接发布 `/cmd_vel`。
- 不直接调用机械臂抓取或放置。
- 不修改 `wpv4_objects_3d`、`wpv4_pt`、`kinect2_bridge` 的原行为。

## 文档

- `docs/01_package_architecture.md`：包结构和节点划分。
- `docs/02_technical_route.md`：椅子、椅面、小铝块、云台的技术路线。
- `docs/03_runtime_inputs_outputs.md`：运行时输入输出话题。
- `docs/04_model_training_boundary.md`：模型训练与运行包的边界。
- `docs/05_field_test_constraints.md`：从实测记录提取的工程约束。

## 阶段 0 烟测

```bash
cd /home/xia/桌面/catkin_ws
catkin_make
source devel/setup.bash
roslaunch colt_bridle fake_scene.launch use_rviz:=true
```

假场景发布：

```text
/colt/bridle/detections
/colt/bridle/source_seat_pose
/colt/bridle/target_seat_pose
/colt/bridle/aluminum_target
/colt/bridle/markers
```

该节点只发布感知和 RViz 调试结果，不发布 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制话题。

## 角色融合 demo

开发机可先用假候选打通角色选择前后的输出链路：

```bash
source devel/setup.bash
roslaunch colt_bridle role_fusion_demo.launch
```

假候选发布：

```text
/colt/bridle/candidates
```

融合节点订阅：

```text
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
```

融合节点发布：

```text
/colt/bridle/detections
/colt/bridle/source_seat_pose
/colt/bridle/target_seat_pose
/colt/bridle/aluminum_target
/colt/bridle/grasp_pose
/colt/bridle/place_pose
/colt/bridle/perception_state
```

手动选择测试：

```bash
rostopic pub -1 /colt/ui/selected_source_chair std_msgs/String "data: 'chair_0'"
rostopic pub -1 /colt/ui/selected_target_chair std_msgs/String "data: 'chair_1'"
```

该 demo 只发布候选、状态和位姿，不发布 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制话题。

## 一键开发机 demo

完整旁路链路可在开发机直接启动：

```bash
source devel/setup.bash
roslaunch colt_bridle bridle_demo.launch use_rviz:=false
```

默认会选择 `chair_0` 作为源椅、`chair_1` 作为目标椅，并输出：

```text
/colt/bridle/detections
/colt/bridle/markers
/colt/bridle/source_seat_pose
/colt/bridle/target_seat_pose
/colt/bridle/aluminum_target
/colt/bridle/grasp_pose
/colt/bridle/place_pose
/colt/bridle/pt_view_goal
/colt/bridle/perception_state
```

部署到实测机后，第一步替换 `/colt/bridle/candidates` 的来源：用真实 detector 发布同类型 `Detection3DArray`，其余 UI 选择、融合、RViz 和观察目标规划节点可以保持不变。

`/colt/bridle/pt_view_goal` 只是期望观察的空间点，不是云台角度命令；真实云台控制必须由后续安全转发器实现。

## 阶段 1 采集脚本

实测机先启动真实硬件基础链路：

```bash
cd /colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_hardware.launch
```

该 launch 会启动 Kinect2、云台状态节点、`joint_state_publisher` 和 `robot_state_publisher`。注意：`wpv4_pt` 启动时可能让云台回到零位，现场必须确认零位动作安全。

采集使用实测专用 launch：

```bash
cd /colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_capture_session.launch
```

默认订阅 QHD 相机数据：

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

默认处于暂停状态，并打开实测机本地 OpenCV 控制面板。现场按键：

```text
s: start/resume
p: pause
q: finish
f: set far_chair
c: set near_chair_aluminum
a: mark aluminum_present
n: mark aluminum_absent
m: toggle motion_base
o: toggle arm_occlusion
```

采集只分两类主场景：

```text
far_chair: 远距离多椅子数据，服务导航接近和椅子多实例检测。
near_chair_aluminum: 近距离椅子、椅面和小铝块数据，服务抓取/放置前坐标估计。
```

输出标准 session 文件夹：

```text
session_YYYYMMDD_HHMMSS/
  images/
  depth/
  points/
  camera_info/
  tf/
  preview/
  meta.jsonl
  session.yaml
```

该脚本只保存数据，不发布 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制话题。启动时会记录危险控制话题 publisher；默认策略是发现未允许的 publisher 时强制保持暂停。

## Runtime 包检查

`colt_trainer_py` 导出的 v002 运行时包复制到 `models/runtime/v002/` 后，可先做离线检查：

```bash
python3 src/colt/colt_bridle/scripts/runtime_package_loader.py --check src/colt/colt_bridle/models/runtime/v002
```

ROS 状态发布：

```bash
source devel/setup.bash
roslaunch colt_bridle runtime_package_loader.launch runtime_dir:=/home/xia/桌面/catkin_ws/src/colt/colt_bridle/models/runtime/v002
```

v002 运行时包至少包含：

```text
chair_seat_seg.onnx
aluminum_roi_seg.onnx
labels.yaml
preprocess.yaml
thresholds.yaml
roi_rules.yaml
release_manifest.json
```

输出：

```text
/colt/bridle/perception_state   colt_msgs/PerceptionState
/colt/bridle/runtime_status     std_msgs/String(JSON)
```

该节点只检查模型包完整性并发布状态，不发布 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制话题。
