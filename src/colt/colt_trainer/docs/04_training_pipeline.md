# 训练流程

## 默认模型

默认训练：

```text
YOLO11l-seg
```

用于上限对比：

```text
YOLO11x-seg
```

如果实测机推理压力过大，运行时再考虑：

```text
YOLO11m-seg
YOLO11s-seg
TensorRT/OpenVINO 加速
降低输入尺寸
降低推理频率
```

当前训练设备是高性能 Windows CUDA 电脑，第一版训练应优先准确性和稳定性，不优先选择过小模型。

训练机使用已经调好的默认 Python 环境，不强制 Conda、venv、Docker 或 WSL。

## 训练输入

```text
prepared/chair_aluminum_vXXX/dataset.yaml
```

类别顺序：

```text
0: chair
1: chair_seat
2: aluminum_block
```

## 推荐输入尺寸

第一轮：

```text
imgsz: 1024 或 1280
```

原因：

- 小铝块目标小，过低分辨率会损失边缘。
- 小车运动视角变化大，小铝块目标小，较高输入分辨率更利于召回。

若显存不足：

```text
imgsz: 960
```

## 增强策略

允许：

- 亮度、对比度、色温变化。
- 轻微旋转和平移。
- 轻微模糊。
- 局部遮挡。
- 背景干扰。

谨慎使用：

- 强 mosaic。
- 大尺度透视变换。
- 过强颜色扰动。

原因是小铝块与椅面的几何关系重要，过强增强可能破坏任务先验。

## 训练命令模板

外部 Python 项目中的训练入口建议为：

```bash
python scripts/train_seg.py --config configs/train_yolo_seg.yaml
```

## 训练产物

```text
reports/train_runs/chair_aluminum_v001_yolo11l_seg/
  weights/best.pt
  weights/last.pt
  results.csv
  confusion_matrix.png
  val_batch*.jpg
```

## 训练后必须执行

1. 验证集指标评估。
2. 测试集独立评估。
3. 失败样例导出。
4. 深度/点云几何评估。
5. ONNX 导出。
6. 运行时配置生成。
7. 模型卡更新。

未完成这些步骤的模型不能进入 `colt_bridle/models/runtime/`。
