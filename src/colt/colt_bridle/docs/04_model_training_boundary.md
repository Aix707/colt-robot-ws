# 模型训练与运行包边界

## 总原则

`colt_bridle` 是机器人运行时包，不承担训练任务。训练、标注、评估和模型导出应保持独立，避免把 PyTorch、SAM 2、数据集和训练脚本压进实测机运行链路。

```text
训练环境：高性能 Windows CUDA 电脑，使用 /home/xia/桌面/colt_trainer_py
运行环境：实测机，只加载导出的 ONNX 和轻量配置
```

## 推荐边界

### 运行包 `colt_bridle`

允许包含：

```text
models/runtime/v*/chair_seg.onnx
models/runtime/v*/chair_seat_roi_seg.onnx
models/runtime/v*/aluminum_roi_seg.onnx
models/runtime/v*/labels.yaml
models/runtime/v*/preprocess.yaml
models/runtime/v*/thresholds.yaml
models/runtime/v*/roi_rules.yaml
models/runtime/v*/model_card.md
```

运行时依赖：

```text
rospy
message_filters
OpenCV
tf2_ros
sensor_msgs
geometry_msgs
colt_msgs
ultralytics
supervision
```

可选推理后端：

```text
cv2.dnn
onnxruntime
TensorRT/OpenVINO
```

不允许包含：

```text
训练集原图
标注工程
PyTorch 训练代码
SAM 2 实时依赖
实验性 notebook
```

### 独立训练工程

训练、标注和评估的设计入口在：

```text
colt/colt_trainer/
```

实际可打包到 Windows CUDA 电脑运行的 Python 项目在：

```text
/home/xia/桌面/colt_trainer_py
```

它可以包含：

```text
datasets/
annotations/
scripts/prepare_dataset.py
scripts/train_seg.py
scripts/export_runtime.py
scripts/evaluate_geometry.py
reports/
```

训练完成后只把导出产物复制到 `colt_bridle/models/runtime/`。

运行包接收的最小 v001 runtime 目录由 `detector_node.py --check` 检查：

```text
chair_seg.onnx
chair_seat_roi_seg.onnx
aluminum_roi_seg.onnx
labels.yaml
preprocess.yaml
thresholds.yaml
roi_rules.yaml
release_manifest.json
```

预检只检查 runtime 目录结构，不发布运动控制。

## 模型产物规范

每个上线模型至少包含：

```text
chair_seg.onnx
chair_seat_roi_seg.onnx
aluminum_roi_seg.onnx
labels.yaml
preprocess.yaml
thresholds.yaml
roi_rules.yaml
model_card.md
metrics.json
```

`model_card.md` 需要记录：

- 训练数据日期和场景。
- 类别列表。
- 输入尺寸。
- 训练/验证指标。
- 已知失败场景。
- 推荐阈值。
- 是否支持椅面 mask。
- 是否支持小铝块 mask。

## v001/v002 边界

当前 `v001` 是实测联调用的三阶段 ROI 模型版本。`v002` 是在 v001 实测失败样例基础上补采、补标后的下一轮稳定版本。

训练和运行都保持三级 ROI：

```text
chair_v001:
  整图输入，输出 chair。

chair_seat_roi_v001:
  chair ROI 输入，输出 chair_seat。

aluminum_roi_v001:
  只接收 seat ROI，输出 aluminum_block 或无目标。
```

小铝块模型不在整图开放搜索。运行时必须先得到 chair ROI，再得到椅面 ROI，把 ROI 内的小铝块结果逐级映射回原图，最后结合 QHD depth/points 和椅面约束得到坐标。

## 数据闭环

实测机只负责采集和实时推理：

```text
采集 rosbag / 图片 / 标注候选
  -> 导出标准 session 文件夹
  -> 复制到 Windows CUDA 电脑
  -> colt_trainer_py 预处理、标注和训练
  -> 导出 ONNX
  -> 回传实测机
  -> colt_bridle 实时推理
```

这样可以保证：

- 实测机环境简单。
- 运行包可复现。
- 模型升级不破坏 ROS 节点接口。
- 后续 UI、导航、机械臂无需关心训练细节。
