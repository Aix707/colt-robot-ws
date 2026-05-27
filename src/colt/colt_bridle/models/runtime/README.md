# runtime 目录

这里存放 Colt 检测 runtime。

当前约定：

```text
models/runtime/current/
  chair_seg.onnx
  chair_seat_roi_seg.onnx
  aluminum_roi_seg.onnx
  release_manifest.json
  preprocess.yaml
  thresholds.yaml
  roi_rules.yaml
```

`detector_node.py --check <runtime_dir>` 会直接检查这些文件。
