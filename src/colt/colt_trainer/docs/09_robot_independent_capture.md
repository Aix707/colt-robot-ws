# 实测机独立采集设计

## 目标

实测机采集必须可以独立进行，输出 Windows 训练项目可直接读取的标准 session 文件夹。采集脚本不依赖训练环境，不启动底盘、机械臂或抓取链路。

## 已落地脚本

```text
colt_bridle/scripts/colt_capture_session.py
```

启动方式：

```bash
roslaunch colt_bridle field_capture_session.launch
```

默认暂停，打开实测机本地 OpenCV 控制面板。按 `s` 开始采集，按 `p` 暂停，按 `q` 结束并写入 `session.yaml`。

脚本当前作为 `colt_bridle` 的采集工具落地；若后续需要独立工具包，再迁移到 `colt_tools/robot_capture/`。

## 输入话题

默认 QHD：

```text
/kinect2/qhd/image_color_rect
/kinect2/qhd/image_depth_rect
/kinect2/qhd/points
/kinect2/qhd/camera_info
/tf
/joint_states
/wpv4_pt/raw_joint_states
```

可选短时 HD：

```text
/kinect2/hd/image_color_rect
/kinect2/hd/points
```

## 输出格式

```text
session_YYYYMMDD_HHMMSS/
  images/
    000001.png
  depth/
    000001.png 或 000001.npy
  points/
    000001.npz 或 000001.pcd
  camera_info/
    000001.yaml
  tf/
    000001.yaml
  preview/
    000001.jpg
  meta.jsonl
  session.yaml
```

`meta.jsonl` 每行记录一帧：

```json
{
  "frame_id": 1,
  "stamp": 1778840000.0,
  "image": "images/000001.png",
  "depth": "depth/000001.npy",
  "points": "points/000001.npz",
  "camera_info": "camera_info/000001.yaml",
  "tf": "tf/000001.yaml",
  "capture_mode": "near_chair_aluminum",
  "scene_tags": ["near_chair_aluminum", "aluminum_present", "motion_base"],
  "pt_pan_deg": 0.0,
  "pt_tilt_deg": 0.0
}
```

## 操作方式

建议支持键盘命令：

```text
s: start / resume
p: pause
q: finish and write session summary
f: far_chair
c: near_chair_aluminum
a: aluminum_present
n: aluminum_absent
m: motion_base
o: arm_occlusion
```

这样现场采集时可以快速给数据打场景标签，后续预处理和分层划分更可靠。

第一批真实采集只分两类主场景：

```text
far_chair:
  远距离多椅子数据，用于训练椅子多实例检测和导航接近前的椅子发现。

near_chair_aluminum:
  近距离椅子、椅面和小铝块数据，用于椅面 ROI、小铝块识别和坐标估计。
```

## 安全边界

采集脚本必须满足：

- 不发布 `/cmd_vel`。
- 不发布 `/wpv4_pt/joint_ctrl_degree`，除非后续明确加入安全云台采集模式。
- 不调用机械臂和抓取节点。
- 启动时检查 `/cmd_vel` 发布者并写入日志。
- TF 不可用时仍可保存 RGB/depth，但该帧标记 `tf_available=false`。

## 与 Windows 训练项目衔接

采集完成后压缩 session：

```bash
tar czf session_YYYYMMDD_HHMMSS.tar.gz session_YYYYMMDD_HHMMSS
```

复制到 Windows 后解压到：

```text
colt_trainer_py/datasets/raw/
```

然后运行：

```powershell
python scripts/prepare_dataset.py --config configs/preprocess.yaml
```
