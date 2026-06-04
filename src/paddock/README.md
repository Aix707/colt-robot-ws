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

真实 ROS 数据上传：

```bash
source devel/setup.bash
roslaunch paddock telemetry_upload.launch
```

开发用模拟现场数据上传：

```bash
source devel/setup.bash
roslaunch paddock telemetry_simulator.launch
```

真实上传可选参数：

```text
server_url:=http://20.194.24.158:2100/api/telemetry
upload_token:=<token>
upload_rate_hz:=1.0
target_frame:=map
robot_frame:=body_link
```

模拟器可选参数：

```text
server_url:=http://20.194.24.158:2100/api/telemetry
upload_token:=<token>
upload_rate_hz:=1.0
frame_id:=map
```

模拟器会持续发送与真实上传相同结构的 JSON，`health.scene_state` 为 `simulated_site`，用于后台和前端开发联调。

真实上传和模拟器都会写入同一个 `server_url`。联调前端时用模拟器；实机运行时用真实上传。不要同时对同一个后台启动两者，除非明确需要用模拟数据覆盖真实数据。

如果与其他项目合并运行，并且外部项目只发布 `base_footprint` 而没有 `body_link`，真实上传启动时传：

```bash
roslaunch paddock telemetry_upload.launch robot_frame:=base_footprint
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
