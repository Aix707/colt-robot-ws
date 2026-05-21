# colt_trainer 定位与边界

## 定位

`colt_trainer` 是离线训练设计入口，不是机器人运行包。实际训练代码放在 catkin 工作空间外的独立 Python 项目：

```text
/home/xia/桌面/colt_trainer_py
```

它负责把实测数据转成可靠模型产物，交给 `colt_bridle` 在机器人上运行。

```text
colt_trainer / colt_trainer_py:
  数据、预处理、标注、训练、评估、导出、模型发布

colt_bridle:
  实时推理、深度/点云融合、TF、状态机、RViz 显示
```

## 为什么必须独立

- 训练依赖重，通常需要 PyTorch、Ultralytics、SAM 2、标注工具和 GPU。
- 当前开发机没有 NVIDIA GPU，正式训练在高性能 Windows CUDA 电脑上进行。
- 实测机运行链路要轻，避免因训练环境污染 ROS 环境。
- 模型迭代频繁，但运行时接口要稳定。
- 后续 UI、导航和机械臂只关心 `colt_bridle` 输出，不应依赖训练细节。

## 输入

```text
RGB 图像
深度图
彩色点云或点云切片
camera_info
TF 或采集时相机/云台姿态
人工标注 mask/bbox
采集元数据
```

实测机采集应导出标准 session 文件夹，而不是只保存 rosbag，方便 Windows 训练项目直接读取。

## 输出

发布给 `colt_bridle` 的运行时模型包：

```text
chair_seat_seg.onnx
aluminum_roi_seg.onnx
labels.yaml
preprocess.yaml
thresholds.yaml
roi_rules.yaml
model_card.md
metrics.json
failure_cases/
```

`v001` 模型只用于辅助标注和补采，正式实机运行包使用 `v002`。运行时推理顺序为：整图椅子/椅面识别，再从椅面附近 ROI 识别小铝块。

## 禁止事项

- 不把训练集原图复制到 `colt_bridle`。
- 不让 `colt_bridle` 依赖 PyTorch 或 SAM 2。
- 不在训练脚本中直接调用 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制接口。
- 不用未评估模型覆盖运行时稳定模型。

## 与其他包关系

```text
colt_trainer
  -> exports runtime model
  -> colt_bridle/models/runtime

colt_bridle
  -> publishes detections/poses/markers
  -> colt_navigation / colt_manipulation / colt_ui
```
