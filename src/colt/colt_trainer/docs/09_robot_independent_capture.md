# 实测机独立采集设计

## 目标

实测机采集必须可以独立进行，输出 Windows 训练项目可读取的标准 session 文件夹。采集脚本不依赖训练环境，不启动底盘、机械臂或抓取链路。

## 已落地脚本

```text
colt_bridle/scripts/colt_capture_session.py
```

启动方式：

```bash
roslaunch colt_bridle capture_session.launch \
  output_root:=/home/robot/colt-robot-ws/data/capture_sessions
```

默认暂停。按 `s` 开始采集，按 `p` 暂停，按 `q` 结束并写入 `session.yaml`。

## 输入话题

默认 QHD：

```text
/kinect2/qhd/image_color_rect
/kinect2/qhd/image_depth_rect
/kinect2/qhd/camera_info
/tf
/tf_static
/joint_states
```

## 输出格式

```text
session_YYYYMMDD_HHMMSS/
  images/
    000001.png
  depth/
    000001.npy
  camera_info/
    000001.yaml
  tf/
    000001.yaml
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
  "camera_info": "camera_info/000001.yaml",
  "tf": "tf/000001.yaml",
  "joint_states": {}
}
```

## 操作方式

```text
s: start / resume
p: pause
q: finish and write session summary
```

## 运行边界

采集脚本只负责保存数据：

- 不发布底盘、云台、机械臂或抓取命令。
- 不检查或阻断其他节点的控制话题。
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
