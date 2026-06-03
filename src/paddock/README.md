# paddock

`paddock` 是 Colt 的 ROS 侧遥测上传包。它只读取现有 ROS 数据并上传服务器，不发布运动控制话题。

## 输入

```text
/colt/bridle/detections
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
/colt/ui/pt_state
TF: map <- body_link
```

## 启动

```bash
source devel/setup.bash
roslaunch paddock telemetry_upload.launch \
  server_url:=http://your-server:8000/api/telemetry
```

可选参数：

```text
upload_token:=<token>
upload_rate_hz:=1.0
target_frame:=map
robot_frame:=body_link
```

## JSON

上传内容包含：

- `robot`：小车 `x/y/yaw`、坐标系和 `tf_ok`
- `selection`：source、target、pt_state
- `objects`：`Detection3DArray` 中的 chair/seat/item
- `health`：上传时间、检测时间和场景状态

## 边界

- 不发布 `/cmd_vel`
- 不发布 `/wpv4_pt/joint_ctrl_degree`
- 不发布机械臂控制话题或 action
- 服务器不可达时只打印节流日志，不影响感知和云台控制
