# 模型导出与发布

## 发布目标

把训练得到的模型转成 `colt_bridle` 可直接加载的运行时包。

训练和导出在外部 Python 项目中完成：

```text
/home/xia/桌面/colt_trainer_py
```

目标目录：

```text
/home/xia/桌面/catkin_ws/src/colt/colt_bridle/models/runtime/
```

## 导出内容

每次发布必须包含：

```text
chair_aluminum_seg.onnx
labels.yaml
preprocess.yaml
thresholds.yaml
model_card.md
metrics.json
release_manifest.json
failure_cases/
```

## ONNX 导出

命令模板：

```bash
python scripts/export_runtime.py --config configs/export_runtime.yaml
```

## 运行时配置

### `labels.yaml`

```yaml
classes:
  0: chair
  1: chair_seat
  2: aluminum_block
```

### `preprocess.yaml`

```yaml
input_size: 1280
color_order: rgb
normalize: true
letterbox: true
```

### `thresholds.yaml`

```yaml
chair:
  confidence: 0.60
  mask_min_area: 2000
chair_seat:
  confidence: 0.55
  mask_min_area: 1000
aluminum_block:
  confidence: 0.70
  mask_min_area: 50
geometry:
  min_depth_valid_ratio: 0.35
  min_seat_plane_inliers: 80
  max_aluminum_height_above_seat_m: 0.08
history:
  max_seat_jump_m: 0.15
  max_aluminum_jump_m: 0.08
  stable_frames: 3
object_priors:
  aluminum_block:
    nominal_diameter_m: 0.05
    nominal_height_m: 0.05
    exact_size_required: false
runtime:
  detection_rate_hz: manual_tune_after_field_test
```

阈值不是训练指标，应由离线验证和实机验证共同调整。

## 发布流程

```text
训练 best.pt
  -> 测试集评估
  -> 深度/点云几何评估
  -> 导出 ONNX
  -> ONNX 离线推理一致性检查
  -> 生成配置和模型卡
  -> 复制到 colt_bridle/models/runtime/
  -> 实测机短时推理验证
```

## 发布清单

`release_manifest.json` 应包含：

```json
{
  "model_name": "chair_aluminum_seg",
  "version": "v001",
  "created_at": "2026-05-20",
  "weights_source": "reports/train_runs/chair_aluminum_v001_yolo11l_seg/weights/best.pt",
  "training_machine": "windows_cuda",
  "dataset_version": "chair_aluminum_v001",
  "classes": ["chair", "chair_seat", "aluminum_block"],
  "input_size": 1280,
  "export_format": "onnx",
  "intended_runtime_package": "colt_bridle"
}
```

## 回滚策略

不要覆盖旧模型目录。建议：

```text
models/runtime/current -> chair_aluminum_v001
models/runtime/chair_aluminum_v001/
models/runtime/chair_aluminum_v002/
```

如果新模型实机效果更差，只切回 `current` 指向旧版本。
