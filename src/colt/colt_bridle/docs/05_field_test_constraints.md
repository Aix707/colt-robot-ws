# 从实测记录提取的开发约束

信息来源：`/home/xia/桌面/kinect2_camera_dev_record/testing/kinect2_camera_test_plan/05_actual_test_record.md`。

## 实测硬件与环境

```text
实测机: robot@10.169.113.176
hostname: WP
远端 Colt 工作区: /home/robot/colt-robot-ws
旧远端测试工作区: /home/robot/catkin_ws_camera_test
Kinect 序列号: 011319650247
云台设备: /dev/wpv4_pt -> ttyUSB2
本地桌面显示: DISPLAY=:1, XAUTHORITY=/run/user/1000/gdm/Xauthority
```

当前开发必须默认：

- 只测试相机、云台和感知。
- 不启动机械臂、抓取和底盘运动链路。
- Colt 当前采集流程不接管底盘；若现场另有底盘控制，由操作者自行确认。

## 相机实测结论

阶段 1 结果：

```text
/kinect2/qhd/image_color_rect: 约 30 Hz
/kinect2/qhd/image_depth_rect: 约 10 Hz
/kinect2/sd/points: 约 10 Hz
```

阶段 3 结果：

```text
/kinect2/sd/points: 约 9.5 Hz
/kinect2/qhd/points: 约 5 Hz
/kinect2/hd/points: 约 3-4 Hz，偶发长间隔
```

2026-05-22 Colt 第一次正式采集前检查：

```text
/kinect2/qhd/image_color_rect: 约 29.9 Hz
/kinect2/qhd/image_depth_rect: 约 9.9 Hz
/kinect2/qhd/points: 约 9.9 Hz
```

开发决策：

- 第一版实时主输入使用 QHD。
- HD 点云只用于观察、离线标注或短时验证。
- 不默认录完整 HD bag，避免磁盘快速增长；实测中短时间曾增长到约 25G。

## TF 实测结论

直接启动 `wpv4_pt + robot_state_publisher` 时，Kinect optical frame 可能不完整。

原因：

- `wpv4_pt` 只发布 `wp_tilt`、`wp_pitch`。
- URDF 中还有 `kinect_height`、`kinect_pitch` 等非固定关节。
- 需要 `joint_state_publisher` 为缺省关节补零。

开发要求：

```text
base_footprint -> kinect2_rgb_optical_frame 必须可查询
```

可靠启动链路：

```bash
rosrun wpv4_bringup wpv4_pt _serial_port:=/dev/wpv4_pt /joint_states:=/wpv4_pt/raw_joint_states
rosparam set robot_description "$(cat /home/robot/catkin_ws_camera_test/src/wpv4_bringup/urdf/wpv4_wpm2_pt.urdf)"
rosparam set /joint_state_publisher/source_list "[/wpv4_pt/raw_joint_states]"
rosrun joint_state_publisher joint_state_publisher
rosrun robot_state_publisher robot_state_publisher
```

实测 TF 参考：

```text
base_footprint -> kinect2_rgb_optical_frame
Translation: [0.086, 0.000, 0.731]
RPY degree: [-90.010, -0.000, -90.030]
```

2026-05-22 现场已有旧 `wpv4_velodyne gmapping.launch`、`wpv4_core`、
`robot_state_publisher` 和 RViz 在运行。为避免重名节点和运动链路混用，Colt 采集只旁路启动
Kinect2 和 `colt_capture_session.py`。这种方式下 `/joint_states` 来自旧链路，
`/wpv4_pt/raw_joint_states` 可能为空；采集文件中应允许 `raw_joint_states: null`。

## 云台实测结论

安全循环运动通过：

```text
命令话题: /wpv4_pt/joint_ctrl_degree
反馈话题: /wpv4_pt/raw_joint_states
安全测试速度: [120, 120]
小范围 pan: 约 +/-8 deg
小范围 tilt: 约 +/-5 deg
现场确认: 能观察到小幅度运动
```

开发决策：

- `colt_bridle` 不直接控制真实云台。
- 云台命令先发布为规划结果，再由限幅转发器控制在零位附近 `±15°`。
- 丢失目标时停止跟踪，不做大范围扫描。

## 旧检测节点限制

`wpv4_objects_3d` 在复杂实验室环境和小铝块目标上不稳定。

已知限制：

```text
输入默认偏向 /kinect2/sd/points
x = 0.8 ~ 1.5 m
y = -0.75 ~ 0.75 m
z = -0.05 ~ 0.5 m
物体宽度 < 0.15 m
聚类半径 0.02 m
最少点数 100
```

开发决策：

- 不把 `wpv4_objects_3d` 作为小铝块识别主链路。
- 后续小铝块坐标应来自视觉模型的候选区域和 QHD 点云/椅面平面。
- `wpv4_objects_3d` 只可作为早期对比或调试输入。

## RViz 调试要求

实测中 RViz 报错主要来自 TF 缺失或被其他 bringup 覆盖。

`colt_bridle` 的 RViz 调试输出应包含：

```text
椅子 bbox / mask 轮廓
椅面中心点
椅面 3D 框或 polygon
小铝块中心点
小铝块 bbox / 3D 框
坐标文本
当前状态
```

marker 默认发布：

```text
/colt/bridle/markers
```

禁止让 RViz 调试节点触发运动控制。
