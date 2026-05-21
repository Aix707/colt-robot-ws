# Runtime Model Packages

`colt_bridle` loads exported runtime packages from this directory. Training data,
PyTorch weights and annotation projects do not belong here.

Expected v002 package layout:

```text
models/runtime/v002/
  chair_seat_seg.onnx
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
models/runtime/current -> v002
```

`v001` packages are for assisted annotation and iteration. The online detector
should use `v002` unless a later reviewed model version is promoted.

The loader publishes readiness on:

```text
/colt/bridle/perception_state
/colt/bridle/runtime_status
```

It never publishes `/cmd_vel`, pan-tilt commands, arm commands or grasp commands.
