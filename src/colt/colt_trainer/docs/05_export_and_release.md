# 模型导出与发布

## 发布目标

把 Windows CUDA 训练得到的 `v001` 三模型产物转成 `colt_bridle` 可检查、可加载的运行时包。`v002` 保留给后续补采、补标后的稳定迭代。

训练和导出在外部 Python 项目中完成：

```text
/home/xia/桌面/colt_trainer_py
```

实测机目标目录：

```text
/colt-robot-ws/src/colt/colt_bridle/models/runtime/v001/
```

当前实测联调阶段 `models/runtime/current` 应指向 `v001`。

## 导出内容

每次发布必须包含：

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
release_manifest.json
failure_cases/
```

## ONNX 导出

目标命令模板：

```bash
py -3.13 scripts\export_runtime.py --config configs\export_runtime_v001.yaml --dry-run
py -3.13 scripts\export_runtime.py --config configs\export_runtime_v001.yaml
```

当前外部项目的 `configs/export_runtime.yaml` 默认也指向 v001；`configs/export_runtime_v002.yaml` 当前不要用于本轮实测联调。

## 运行时配置

### `labels.yaml`

可以使用全局类别表：

```yaml
classes:
  0: chair
  1: chair_seat
  2: aluminum_block
```

也可以使用按模型拆分的类别表：

```yaml
models:
  chair:
    classes:
      0: chair
  chair_seat_roi:
    classes:
      0: chair_seat
  aluminum_roi:
    classes:
      0: aluminum_block
```

### `preprocess.yaml`

```yaml
models:
  chair:
    input_size: [1024, 1024]
    color_order: rgb
    normalize: true
    letterbox: true
  chair_seat_roi:
    input_size: [960, 960]
    color_order: rgb
    normalize: true
    letterbox: true
  aluminum_roi:
    input_size: [960, 960]
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
runtime:
  detection_rate_hz: manual_tune_after_field_test
```

### `roi_rules.yaml`

```yaml
seat_roi:
  expand_ratio: 0.30
  min_width_px: 96
  min_height_px: 96
  clamp_to_image: true
chair_roi:
  expand_ratio: 0.12
  min_width_px: 128
  min_height_px: 128
  clamp_to_image: true
aluminum_constraint:
  require_inside_seat_polygon: true
  max_height_above_seat_m: 0.08
  seat_boundary_margin_m: 0.05
```

阈值不是训练指标，应由离线验证和实机验证共同调整。

## 发布流程

```text
训练 chair_v001 best.pt
  -> 生成/确认 chair ROI
  -> 训练 chair_seat_roi_v001 best.pt
  -> 生成/确认 seat ROI
  -> 训练 aluminum_roi_v001 best.pt
  -> 测试集评估
  -> 深度/点云几何评估
  -> 导出三个 ONNX
  -> ONNX 离线推理一致性检查
  -> 生成配置和模型卡
  -> 复制到 colt_bridle/models/runtime/v001/
  -> detector_node.py --check
  -> 实测机短时推理验证
```

## 发布清单

`release_manifest.json` 应包含：

```json
{
  "version": "v001",
  "created_at": "2026-05-22",
  "training_machine": "windows_cuda",
  "dataset_versions": {
    "chair": "chair_v001",
    "chair_seat_roi": "chair_seat_roi_v001",
    "aluminum_roi": "aluminum_roi_v001"
  },
  "models": {
    "chair": {
      "file": "chair_seg.onnx",
      "weights_source": "reports/train_runs/chair_v001_yolo11m_seg_fast-2/weights/best.pt",
      "classes": ["chair"],
      "input_size": 1024
    },
    "chair_seat_roi": {
      "file": "chair_seat_roi_seg.onnx",
      "weights_source": "reports/train_runs/chair_seat_roi_v001_yolo11m_seg_fast-2/weights/best.pt",
      "classes": ["chair_seat"],
      "input_size": 960
    },
    "aluminum_roi": {
      "file": "aluminum_roi_seg.onnx",
      "weights_source": "reports/train_runs/aluminum_roi_v001_yolo11m_seg_fast-2/weights/best.pt",
      "classes": ["aluminum_block"],
      "input_size": 960
    }
  },
  "export_format": "onnx",
  "intended_runtime_package": "colt_bridle"
}
```

## 回滚策略

不要覆盖旧模型目录。建议：

```text
models/runtime/current -> v001
models/runtime/v001/
models/runtime/v002/
models/runtime/v003/
```

如果新模型实机效果更差，只切回 `current` 指向上一个稳定版本。
