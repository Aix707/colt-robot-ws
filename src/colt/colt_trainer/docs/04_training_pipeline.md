# 训练流程

## 默认模型策略

训练在高性能 Windows CUDA 电脑上完成，第一目标是识别准确性和稳定性，不优先选择过小模型。

默认使用：

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

训练机使用已经调好的默认 Python 环境，不强制 Conda、venv、Docker 或 WSL。

## 两阶段训练顺序

训练必须先完成椅子/椅面，再训练小铝块 ROI。两类模型相对独立。

```text
chair_seat_v001:
  整图输入
  类别：chair, chair_seat
  目标：初步识别多把椅子和椅面，用于辅助标注与 ROI 生成

aluminum_roi_v001:
  椅面附近 ROI 输入
  类别：aluminum_block
  目标：初步识别椅面附近小铝块，用于辅助标注

chair_seat_v002 + aluminum_roi_v002:
  v001 辅助补采、补标后训练
  目标：实机实际运行模型
```

`v001` 不作为正式运行模型。`v002` 才能导出到 `colt_bridle/models/runtime/v002/`。

## 训练输入

```text
prepared/chair_seat_vXXX/dataset.yaml
prepared/aluminum_roi_vXXX/dataset.yaml
```

椅子/椅面类别顺序：

```text
0: chair
1: chair_seat
```

小铝块 ROI 类别顺序：

```text
0: aluminum_block
```

小铝块不在整图开放搜索，只在椅面附近 ROI 内训练和推理。

## 推荐输入尺寸

椅子/椅面：

```text
imgsz: 1280
```

小铝块 ROI：

```text
imgsz: 960 或 1280
```

原因：

- 远距离多椅识别需要保持整体结构。
- 小铝块目标小，过低分辨率会损失边缘。
- 小车运动视角变化大，较高输入分辨率更利于召回。

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

外部 Python 项目中的目标训练入口为：

```bash
python scripts/train_seg.py --config configs/train_chair_seat_v001.yaml
python scripts/extract_aluminum_roi.py --config configs/aluminum_roi.yaml
python scripts/train_seg.py --config configs/train_aluminum_roi_v001.yaml
python scripts/train_seg.py --config configs/train_chair_seat_v002.yaml
python scripts/train_seg.py --config configs/train_aluminum_roi_v002.yaml
```

当前若外部项目仍只有旧的 `train_yolo_seg.yaml`，需要先拆分配置后再进入正式训练。

## 训练产物

```text
reports/train_runs/chair_seat_v001_yolo11l_seg/
reports/train_runs/aluminum_roi_v001_yolo11l_seg/
reports/train_runs/chair_seat_v002_yolo11l_seg/
reports/train_runs/aluminum_roi_v002_yolo11l_seg/
```

每个训练目录至少应包含：

```text
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
4. 椅面 ROI 生成质量检查。
5. 深度/点云几何评估。
6. ONNX 导出。
7. 运行时配置生成。
8. 模型卡更新。

未完成这些步骤的模型不能进入 `colt_bridle/models/runtime/`。
