# colt_bridle 运行时输入输出

## 输入话题

### Kinect2

实测推荐第一版使用 QHD：

```text
/kinect2/qhd/image_color_rect   sensor_msgs/Image
/kinect2/qhd/image_depth_rect   sensor_msgs/Image
/kinect2/qhd/points             sensor_msgs/PointCloud2
/kinect2/qhd/camera_info        sensor_msgs/CameraInfo
```

说明：

- SD 点云速度更稳，但细节不足。
- HD 点云更密，但实测约 3-4 Hz，负载高，适合观察和离线验证，不适合作为第一版实时主输入。
- QHD 是实时检测、RViz 显示和坐标计算的折中选择。

### TF 与云台状态

```text
/tf
/tf_static
/joint_states
/wpv4_pt/raw_joint_states
```

TF 必须能查询：

```text
base_footprint -> kinect2_rgb_optical_frame
```

实测中可靠的 TF 链路：

```bash
rosrun wpv4_bringup wpv4_pt _serial_port:=/dev/wpv4_pt /joint_states:=/wpv4_pt/raw_joint_states
rosparam set /joint_state_publisher/source_list "[/wpv4_pt/raw_joint_states]"
rosrun joint_state_publisher joint_state_publisher
rosrun robot_state_publisher robot_state_publisher
```

## 输出话题

第一阶段建议命名：

```text
/colt/bridle/detections         colt_msgs/Detection3DArray
/colt/bridle/source_seat_pose   geometry_msgs/PoseStamped
/colt/bridle/target_seat_pose   geometry_msgs/PoseStamped
/colt/bridle/aluminum_target    geometry_msgs/PoseStamped
/colt/bridle/grasp_pose         geometry_msgs/PoseStamped
/colt/bridle/place_pose         geometry_msgs/PoseStamped
/colt/bridle/perception_state   std_msgs/String 或 colt_msgs/PerceptionState
/colt/bridle/markers            visualization_msgs/MarkerArray
/colt/bridle/debug_image        sensor_msgs/Image
```

源椅和目标椅由后续 UI 人工指定。第一版可先通过参数、服务或临时话题传入角色绑定关系，后续再由 `colt_ui` 正式提供：

```text
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
```

当前阶段 `colt_msgs` 的重点是表达坐标点与框，并由 `rviz_visualizer_node.py` 转换到 `/colt/bridle/markers`。

第一版运行环境由 `colt_bridle` 决定：

```text
ROS Noetic Python3
onnxruntime
OpenCV / cv_bridge
```

TensorRT/OpenVINO 作为后续性能优化路径，不作为第一版强依赖。实时识别频率通过配置手动调整。

## 坐标系

开发阶段默认：

```text
frame_id = base_footprint
```

后续扩展：

```text
arm_base_link: 机械臂抓取和放置
map 或 odom: 小车全局导航
seat_frame: 单把椅面的局部坐标
kinect2_rgb_optical_frame: 相机原始计算
```

所有 `PoseStamped` 必须设置：

```text
header.stamp
header.frame_id
```

## 不允许行为

- 不允许感知节点直接发布 `/cmd_vel`。
- 不允许识别节点直接发布 `/wpv4_pt/joint_ctrl_degree`。
- 不允许无 `frame_id` 的坐标输出。
- 不允许单帧低置信度结果覆盖稳定坐标。
- 不允许遮挡状态下更新抓取点或放置点。
