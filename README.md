# Colt Robot Workspace 操作手册

这是 `Aix707/colt-robot-ws` 的 ROS/catkin 工作空间。当前 Colt 部分用于 Kinect2 相机、二轴云台、椅子/椅面/小铝块识别与坐标输出开发，后续给小车导航、机械臂抓取/放置和 UI 使用。

本文只保留实际会用的操作步骤。

## 1. 当前能做什么

已实现：

- `colt_msgs`：Colt 内部消息接口。
- `colt_bridle`：
  - 实测机硬件基础启动 launch。
  - Kinect2 数据采集脚本。
  - runtime v002 模型包完整性检查。
  - 场景融合、RViz marker、云台观察目标点等后续在线链路组件。
- `colt_ui`：终端选择源椅和目标椅。
- `colt_trainer`：训练流程文档和配置模板。

未完成：

- 真实 `detector_node.py`：加载 v002 模型，从 Kinect2 实时发布 `/colt/bridle/candidates`。
- 真实在线总 launch：一键启动硬件、detector、融合、UI、RViz。
- 云台限幅转发器：把 `/colt/bridle/pt_view_goal` 转成受限云台命令。
- 底盘和机械臂执行链路。

因此当前主线是：

```text
同步代码到实测机
  -> 采集真实数据
  -> Windows 训练机训练 v002
  -> 复制 runtime/v002 回实测机
  -> 补齐真实 detector
  -> 实机在线验证
```

## 2. 目录

```text
catkin_ws/
  AGENTS.md
  README.md
  src/
    colt/
      DEVELOPMENT_FLOW.md
      DOCUMENT_REVIEW.md
      colt_msgs/
      colt_bridle/
      colt_ui/
      colt_trainer/
    iai_kinect2/
    wpv4_bringup/
    wpv4_tutorials/
```

外部训练项目不在本仓库内：

```text
/home/xia/桌面/colt_trainer_py
```

## 3. 开发机检查

```bash
cd /home/xia/桌面/catkin_ws
git status --short --branch
catkin_make
source devel/setup.bash
rospack find colt_msgs
rospack find colt_bridle
rospack find colt_ui
```

`catkin_make` 成功即可。旧工作空间可能仍有 VTK/PCL、TinyXML、旧包 `message_generation` warning；只要没有 error，先继续。

## 4. 同步到实测机

实测机不能访问 GitHub，由开发机同步。当前实测机连接方式：

```text
ssh robot@10.169.113.176
```

2026-05-22 实测时，实际可用工作空间是：

```text
/home/robot/colt-robot-ws
```

旧文档和脚本中可能仍出现 `/colt-robot-ws` 或 `robot@172.20.10.12`。本次实测发现
`/colt-robot-ws` 为空目录，应优先使用 `~/colt-robot-ws`。同步脚本的默认参数若未更新，
需要按实际 IP 和路径覆盖。

```bash
cd /home/xia/桌面/catkin_ws
./scripts/sync_robot_ws.sh
```

实测机编译：

```bash
ssh robot@10.169.113.176
cd ~/colt-robot-ws
catkin_make
source devel/setup.bash
rospack find colt_bridle
```

## 5. 实测机启动相机、云台状态和 TF

独立实测时可用完整硬件基础 launch：

```bash
cd ~/colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_hardware.launch
```

若现场已经有导航、建图或旧 bringup 在运行，不要叠加启动会重名或会接入运动链路的节点。
2026-05-22 实测时现场已有 `wpv4_velodyne gmapping.launch`、`wpv4_core`、
`robot_state_publisher` 和 RViz，因此只在旁路启动 Kinect2：

```bash
cd ~/colt-robot-ws
source devel/setup.bash
screen -L -Logfile /tmp/colt_kinect.log -dmS colt_kinect \
  bash -lc 'cd /home/robot/colt-robot-ws; source devel/setup.bash; roslaunch kinect2_bridge kinect2_bridge.launch'
```

说明：

- 启动 Kinect2。
- 启动 `wpv4_pt` 读取云台状态。
- 启动 `joint_state_publisher` 和 `robot_state_publisher`。
- `wpv4_pt` 可能让云台回零，现场确认无遮挡后再启动。
- 旁路 Kinect2 方式只启动相机，不读取云台原始状态；`raw_joint_states` 可能为空。

检查：

```bash
source ~/colt-robot-ws/devel/setup.bash
rostopic hz /kinect2/qhd/image_color_rect
rostopic hz /kinect2/qhd/image_depth_rect
rostopic hz /kinect2/qhd/points
rostopic echo -n 1 /joint_states
rosrun tf tf_echo base_footprint kinect2_rgb_optical_frame
```

## 6. 实测机采集数据

保持第 5 步运行，另开终端：

```bash
cd ~/colt-robot-ws
source devel/setup.bash
roslaunch colt_bridle field_capture_session.launch
```

若需要把 OpenCV 采集面板显示到实测机本地桌面，先确认桌面显示号。本次实测可用：

```bash
export DISPLAY=:1
export XAUTHORITY=/run/user/1000/gdm/Xauthority
```

推荐用 `screen` 保持采集进程独立于 SSH 连接：

```bash
screen -L -Logfile /tmp/colt_capture.log -dmS colt_capture \
  bash -lc 'cd /home/robot/colt-robot-ws; source devel/setup.bash; export DISPLAY=:1; export XAUTHORITY=/run/user/1000/gdm/Xauthority; roslaunch colt_bridle field_capture_session.launch output_root:=/home/robot/colt-robot-ws/data/capture_sessions'
```

检查和恢复：

```bash
screen -ls
screen -r colt_capture
tail -n 50 /tmp/colt_capture.log
```

默认输出：

```text
/home/robot/colt-robot-ws/data/capture_sessions/
```

按键：

```text
s: 开始/继续
p: 暂停
q: 结束
f: 远距离多椅子 far_chair
c: 近距离椅子+小铝块 near_chair_aluminum
a: 有小铝块 aluminum_present
n: 无小铝块 aluminum_absent
m: 小车运动中 motion_base
o: 机械臂遮挡 arm_occlusion
```

只采两类主数据：

- `far_chair`：远距离、多把椅子。
- `near_chair_aluminum`：近距离、椅子/椅面/小铝块。

输出结构：

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

采集脚本只保存数据，不发布底盘、云台或机械臂命令。

## 7. 数据传回开发机

采集结束后，先确认 session 已正常关闭：

```bash
ssh robot@10.169.113.176
cd ~/colt-robot-ws
sed -n '1,40p' data/capture_sessions/session_YYYYMMDD_HHMMSS/session.yaml
```

`final: true` 且 `frame_count` 正确后，在开发机拉回仓库内的忽略数据目录：

```bash
cd /home/xia/桌面/catkin_ws
mkdir -p src/colt/colt_trainer/datasets/raw
rsync -av --partial --progress \
  robot@10.169.113.176:/home/robot/colt-robot-ws/data/capture_sessions/session_YYYYMMDD_HHMMSS/ \
  /home/xia/桌面/catkin_ws/src/colt/colt_trainer/datasets/raw/session_YYYYMMDD_HHMMSS/
```

本次第一次正式采集为：

```text
session_20260522_142754
frame_count: 215
size: about 1.2G
capture_mode: near_chair_aluminum
```

本地数据目录 `src/colt/colt_trainer/datasets/` 已被 `.gitignore` 忽略，不要提交原始数据。

## 8. 数据转到 Windows 训练机

实测机打包：

```bash
cd ~/colt-robot-ws/data/capture_sessions
tar czf session_YYYYMMDD_HHMMSS.tar.gz session_YYYYMMDD_HHMMSS
```

复制到 Windows 后，放入：

```text
colt_trainer_py/datasets/raw/
```

在 Windows 训练机进入 `colt_trainer_py`，按顺序运行：

```powershell
python scripts/prepare_dataset.py --config configs/preprocess.yaml
python scripts/train_seg.py --config configs/train_chair_seat_v001.yaml
python scripts/extract_aluminum_roi.py --config configs/aluminum_roi.yaml
python scripts/train_seg.py --config configs/train_aluminum_roi_v001.yaml
python scripts/train_seg.py --config configs/train_chair_seat_v002.yaml
python scripts/train_seg.py --config configs/train_aluminum_roi_v002.yaml
python scripts/export_runtime.py --config configs/export_runtime_v002.yaml
```

训练顺序：

1. 先训练椅子/椅面。
2. 根据椅面结果截取 ROI。
3. 再训练小铝块 ROI。
4. `v001` 用于辅助标注和补采。
5. `v002` 用于实机运行。

## 9. 发布 v002 runtime 到实测机

训练导出应得到：

```text
exports/colt_runtime_v002/runtime/
  chair_seat_seg.onnx
  aluminum_roi_seg.onnx
  labels.yaml
  preprocess.yaml
  thresholds.yaml
  roi_rules.yaml
  metrics.json
  model_card.md
  release_manifest.json
```

复制到当前工作空间并检查：

```bash
cd /home/xia/桌面/catkin_ws
./scripts/install_runtime.sh /path/to/exports/colt_runtime_v002/runtime v002
```

再同步到实测机：

```bash
./scripts/sync_robot_ws.sh
```

通过标准：`install_runtime.sh` 输出 JSON 中 `"ready": true`。

也可以发布 ROS 状态：

```bash
roslaunch colt_bridle runtime_package_loader.launch runtime_dir:=/home/robot/colt-robot-ws/src/colt/colt_bridle/models/runtime/v002
```

## 10. 项目还需要继续简化和补齐

当前仍然需要补齐：

- `detector_node.py`：真实模型推理与 3D 坐标估计。
- `online_perception.launch`：实测在线一键启动。
- `pt_limited_forwarder_node.py`：云台限幅 `±15°` 转发。

若某一步现场操作仍然很长，应优先把它做成脚本或 launch，而不是继续堆文档。
