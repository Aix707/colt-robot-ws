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

## 阶段 1 采集脚本

```bash
cd /home/xia/桌面/catkin_ws
catkin_make
source devel/setup.bash
roslaunch colt_bridle capture_session.launch output_root:=/home/robot/colt_capture_sessions
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

默认处于暂停状态，现场按键：

```text
s: start/resume
p: pause
q: finish
1: toggle source_chair
2: toggle target_chair
a: mark aluminum_present
n: mark aluminum_absent
m: toggle motion_approach
o: toggle arm_occlusion
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

该脚本只保存数据，不发布 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制话题。

## Runtime 包检查

`colt_trainer_py` 导出的运行时包复制到 `models/runtime/<version>/` 后，可先做离线检查：

```bash
python3 src/colt/colt_bridle/scripts/runtime_package_loader.py --check src/colt/colt_bridle/models/runtime/<version>
```

ROS 状态发布：

```bash
source devel/setup.bash
roslaunch colt_bridle runtime_package_loader.launch runtime_dir:=/home/xia/桌面/catkin_ws/src/colt/colt_bridle/models/runtime/<version>
```

输出：

```text
/colt/bridle/perception_state   colt_msgs/PerceptionState
/colt/bridle/runtime_status     std_msgs/String(JSON)
```

该节点只检查模型包完整性并发布状态，不发布 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制话题。
