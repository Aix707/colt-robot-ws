# Colt 开发文档审查记录

日期：2026-05-20

## 已审查范围

```text
/home/xia/桌面/catkin_ws/src/colt/
/home/xia/桌面/colt_trainer_py/
/home/xia/桌面/kinect2_camera_dev_record/
```

重点审查：

- `colt_msgs` 接口设计。
- `colt_bridle` 技术路线、输入输出、训练边界、实测约束。
- `colt_trainer` 数据、预处理、标注、训练、导出、评估、采集设计。
- `colt_trainer_py` Windows CUDA 独立训练项目。
- 桌面开发记录中的总体路线、接口、推进计划。

## 已发现并修正的问题

### 1. 旧测试命名与正式接口混用

问题：

```text
/kinect_pt_test/*
```

仍在开发记录中作为主接口出现。

处理：

- 正式开发接口统一为：

```text
/colt/bridle/*
```

- `/kinect_pt_test/*` 仅作为阶段 4 历史测试原型记录保留。

### 2. 训练环境描述不准确

问题：

- 文档中仍有“开发机训练”的表述。
- 现在已确认开发机无 NVIDIA GPU。

处理：

- 统一改为 Windows CUDA 电脑训练。
- 实际训练项目为：

```text
/home/xia/桌面/colt_trainer_py
```

### 3. 模型默认路线前后不一致

问题：

- 部分文档仍写 `YOLO11m-seg first`。

处理：

- 默认训练改为 `YOLO11l-seg`。
- 需要上限对比时使用 `YOLO11x-seg`。
- `YOLO11m/s-seg` 仅作为实测机部署压力过大时的 fallback。

### 4. 训练脚本名不一致

问题：

- 文档中存在 `train_seg_model.py`、`export_onnx.py`，但独立 Python 项目使用 `train_seg.py`、`export_runtime.py`。

处理：

- 统一命令为：

```text
python scripts/train_seg.py --config configs/train_yolo_seg.yaml
python scripts/export_runtime.py --config configs/export_runtime.yaml
```

- 新增占位脚本：

```text
scripts/auto_annotate.py
scripts/evaluate_geometry.py
```

### 5. 源椅/目标椅职责不清

问题：

- 有些描述容易理解为模型需要区分源椅和目标椅。

处理：

- 明确模型只检测：

```text
chair
chair_seat
aluminum_block
```

- 源椅和目标椅由后续 UI 人工指定，`colt_bridle` 负责绑定对应坐标。

### 6. 缺少权威开发顺序

问题：

- 各文档有阶段描述，但没有一个统一的执行顺序基准。

处理：

- 新增：

```text
/home/xia/桌面/catkin_ws/src/colt/DEVELOPMENT_FLOW.md
```

后续开发顺序以该文件为准。

## 当前确定开发顺序

```text
1. 实现 colt_msgs + RViz 假数据显示
2. 实现实测机独立采集脚本
3. 采集中等数据量完整 session
4. 实现 colt_trainer_py 预处理
5. 完成 v001 辅助标注
6. 训练 YOLO11l-seg v001
7. 做离线几何评估
8. 实现 colt_bridle 最小在线链路
9. 实机静态验证
10. 用 v001 模型辅助补采和补标，迭代 v002
11. 再开发 UI 选择、云台辅助、导航/机械臂预览
```

## 当前非阻塞记录项

这些问题不阻塞阶段 0 和阶段 1，只需在后续采集或训练报告中记录：

1. 椅面颜色或材质：在采集 `session.yaml` 中记录即可。
2. Windows 训练机显卡型号和显存：第一次训练报告中记录即可。

已确认并纳入路线：

- 小铝块可以在椅面任意位置，不使用固定放置区域假设。
- 小铝块可能被遮挡，遮挡时需要云台换视角与历史坐标约束。
- 先采中等数据量，训练 v001 初版模型，再用 v001 加速后续半自动标注。
- 用户有 LabelMe AI 辅助标注经验，`colt_trainer_py` 的半自动标注流程优先兼容 LabelMe JSON、COCO、YOLO segmentation 转换。
- 实测机运行环境由开发方决定：默认 ROS Noetic Python3 + `onnxruntime`，TensorRT/OpenVINO 后续优化。

## 结论

当前文档结构已经可以支持实际开发启动。建议下一步先实现 `colt_msgs` 和 RViz 假数据显示，再实现实测机独立采集脚本。第一轮采集按中等数据量执行，用 v001 模型进入主动学习循环。
