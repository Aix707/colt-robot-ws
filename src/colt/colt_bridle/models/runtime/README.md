# Runtime Model Packages

`colt_bridle` loads exported runtime packages from this directory. Training data,
PyTorch weights and annotation projects do not belong here.

Expected package layout:

```text
models/runtime/chair_aluminum_v001/
  chair_aluminum_seg.onnx
  labels.yaml
  preprocess.yaml
  thresholds.yaml
  metrics.json
  model_card.md
  release_manifest.json
  failure_cases/
```

Recommended deployment pattern:

```text
models/runtime/current -> chair_aluminum_v001
```

The loader publishes readiness on:

```text
/colt/bridle/perception_state
/colt/bridle/runtime_status
```

It never publishes `/cmd_vel`, pan-tilt commands, arm commands or grasp commands.
