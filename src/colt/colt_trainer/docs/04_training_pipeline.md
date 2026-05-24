# 训练流程

## 默认模型策略

训练在高性能 Windows CUDA 电脑上完成，第一目标是识别准确性和稳定性。当前 v001 已验证使用：

```text
YOLO11m-seg
batch: 4
```

原因是当前 Windows 训练机为 RTX 4060 Laptop GPU 8GB，`YOLO11l-seg + batch:auto` 容易过慢或触发 AutoBatch CUDA OOM。

用于后续上限对比：

```text
YOLO11l-seg
YOLO11x-seg
```

如果实测机推理压力过大，运行时再考虑：

```text
YOLO11s-seg
TensorRT/OpenVINO 加速
降低输入尺寸
降低推理频率
```

训练机使用已经调好的默认 Python 环境，不强制 Conda、venv、Docker 或 WSL。

## 三级 ROI 训练顺序

训练必须先完成整图 chair，再训练 chair ROI 内 chair_seat，最后训练 seat ROI 内小铝块。三个模型相对独立。

```text
chair_v001:
  整图输入
  类别：chair
  目标：识别多把椅子，用于生成 chair ROI

chair_seat_roi_v001:
  chair ROI 输入
  类别：chair_seat
  目标：识别椅面，用于几何评估与 seat ROI 生成

aluminum_roi_v001:
  seat ROI 输入
  类别：aluminum_block
  目标：识别椅面附近小铝块
```

`v001` 已作为当前实测联调模型导出到 `colt_bridle/models/runtime/v001/`。`v002` 保留给后续补采、补标后的稳定训练周期。

## 训练输入

```text
prepared/chair_vXXX/dataset.yaml
prepared/chair_seat_roi_vXXX/dataset.yaml
prepared/aluminum_roi_vXXX/dataset.yaml
```

整图椅子类别顺序：

```text
0: chair
```

chair ROI 椅面类别顺序：

```text
0: chair_seat
```

小铝块 ROI 类别顺序：

```text
0: aluminum_block
```

小铝块不在整图开放搜索，只在椅面附近 ROI 内训练和推理。

## 推荐输入尺寸

整图 chair：

```text
imgsz: 1024
```

chair ROI 椅面：

```text
imgsz: 960
```

小铝块 ROI：

```text
imgsz: 960
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
py -3.13 scripts\make_dataset_view.py --config configs\derive_chair_v001.yaml
py -3.13 scripts\auto_annotate.py --config configs\auto_annotation_chair.yaml --mode convert-labelme
py -3.13 scripts\train_seg.py --config configs\train_chair_v001.yaml
py -3.13 scripts\extract_label_roi.py --config configs\chair_roi.yaml
py -3.13 scripts\auto_annotate.py --config configs\auto_annotation_chair_seat_roi.yaml --mode convert-labelme
py -3.13 scripts\train_seg.py --config configs\train_chair_seat_roi_v001.yaml
py -3.13 scripts\extract_aluminum_roi.py --config configs\aluminum_roi.yaml
py -3.13 scripts\auto_annotate.py --config configs\auto_annotation_aluminum_roi.yaml --mode convert-labelme
py -3.13 scripts\train_seg.py --config configs\train_aluminum_roi_v001.yaml
```

当前外部项目已经拆分了 `train_chair_v001.yaml`、`train_chair_seat_roi_v001.yaml` 和 `train_aluminum_roi_v001.yaml`。

## 训练产物

```text
reports/train_runs/chair_v001_yolo11m_seg_fast-2/
reports/train_runs/chair_seat_roi_v001_yolo11m_seg_fast-2/
reports/train_runs/aluminum_roi_v001_yolo11m_seg_fast-2/
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
