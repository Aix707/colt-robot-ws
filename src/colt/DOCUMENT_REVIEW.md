# Colt 开发文档审查记录

日期：2026-05-20；2026-05-24 根据 `colt_trainer_py` 当前三级 ROI 流程补充修订。

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

- 早期文档在 `YOLO11m-seg first`、`YOLO11l-seg` 默认和 v002 双模型路线之间不一致。

处理：

- 当前 v001 实测联调按 `YOLO11m-seg`、固定 `batch: 4` 训练三阶段 ROI 模型。
- `YOLO11l-seg` 和 `YOLO11x-seg` 保留为后续数据量扩大后的上限对比。
- `v002` 保留为 v001 实测失败样例补采、补标后的下一轮稳定版本。

### 4. 训练脚本名不一致

问题：

- 文档中存在 `train_seg_model.py`、`export_onnx.py`，但独立 Python 项目使用 `train_seg.py`、`export_runtime.py`。

处理：

- 统一命令为：

```text
py -3.13 scripts\make_dataset_view.py --config configs\derive_chair_v001.yaml
py -3.13 scripts\train_seg.py --config configs\train_chair_v001.yaml
py -3.13 scripts\extract_label_roi.py --config configs\chair_roi.yaml
py -3.13 scripts\train_seg.py --config configs\train_chair_seat_roi_v001.yaml
py -3.13 scripts\extract_aluminum_roi.py --config configs\aluminum_roi.yaml
py -3.13 scripts\train_seg.py --config configs\train_aluminum_roi_v001.yaml
py -3.13 scripts\export_runtime.py --config configs\export_runtime_v001.yaml
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

- 明确模型不区分源椅/目标椅，只检测任务语义类别：

```text
chair
chair_seat
aluminum_block
```

- 源椅和目标椅由后续 UI 人工指定，`colt_bridle` 负责绑定对应坐标。
- 小铝块模型不做整图开放搜索，只在椅面附近 ROI 内运行。

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
1. 实现 colt_msgs
2. 实现实测机独立采集脚本
3. 采集中等数据量完整 session
4. 实现 colt_trainer_py 预处理
5. 完成 chair_seat_v001 辅助标注
6. 派生并训练 chair_v001，生成 chair_seat_roi_v001 数据
7. 训练 chair_seat_roi_v001，生成 aluminum_roi_v001 数据
8. 训练 aluminum_roi_v001
9. 做离线几何评估并导出 runtime/v001
10. 实现 colt_bridle 最小在线链路
11. 实机静态验证
12. 基于实测失败样例迭代 v002，再开发 UI 选择、云台辅助、导航/机械臂预览
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

当前文档结构已经可以支持实际开发启动。下一步优先推进实测机独立采集、训练数据处理和真实 detector 开发。第一轮采集按中等数据量执行，用 v001 模型进入主动学习循环。
