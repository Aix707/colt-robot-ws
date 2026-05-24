# Runtime Model Packages

`colt_bridle` loads exported runtime packages from this directory. Training data,
PyTorch weights and annotation projects do not belong here.

Expected current v001 package layout:

```text
models/runtime/v001/
  chair_seg.onnx
  chair_seat_roi_seg.onnx
  aluminum_roi_seg.onnx
  labels.yaml
  preprocess.yaml
  thresholds.yaml
  roi_rules.yaml
  metrics.json
  model_card.md
  release_manifest.json
  failure_cases/
```

Recommended deployment pattern:

```text
models/runtime/current -> v001
```

The current field-integration detector should use the v001 three-stage ROI
package: full-image `chair`, chair-ROI `chair_seat`, then seat-ROI
`aluminum_block`. `v002` is reserved for the next iteration after collecting
and labeling field failure cases.

The loader publishes readiness on:

```text
/colt/bridle/perception_state
/colt/bridle/runtime_status
```

It never publishes `/cmd_vel`, pan-tilt commands, arm commands or grasp commands.
