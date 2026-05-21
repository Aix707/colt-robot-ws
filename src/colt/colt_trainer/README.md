# colt_trainer 开发文档

`colt_trainer` 是 Colt 系统的离线训练设计入口，用于约定数据采集、预处理、标注、训练、评估、导出和模型版本发布。它与机器人实时运行包 `colt_bridle` 分离，训练依赖不进入实测机运行链路。

实际可打包运行的 Python 训练项目放在 catkin 工作空间外：

```text
/home/xia/桌面/colt_trainer_py
```

该项目用于复制到高性能 Windows CUDA 电脑上训练。

## 职责

- 整理 Kinect2 实测数据、RGB 图像、深度图、点云和标注文件。
- 定义原始 session 到训练集的预处理流程。
- 训练椅子、椅面、小铝块实例分割模型。
- 使用深度/点云信息做训练数据质检和评估增强。
- 导出 `colt_bridle` 可加载的 ONNX 模型和运行时配置。
- 生成模型卡、指标报告、失败样例和发布清单。

## 不负责

- 不在机器人实时链路中运行。
- 不发布 ROS 运动控制话题。
- 不直接控制云台、小车或机械臂。
- 不替代 `colt_bridle` 的 TF 转换和 RViz 显示节点。

## 文档

- `docs/01_role_and_boundaries.md`：包定位和边界。
- `docs/02_dataset_design.md`：数据集结构、类别和采集要求。
- `docs/03_annotation_workflow.md`：标注流程和质检规则。
- `docs/04_training_pipeline.md`：训练流程和配置。
- `docs/05_export_and_release.md`：ONNX 导出和发布到 `colt_bridle`。
- `docs/06_evaluation_acceptance.md`：评估指标和通过标准。
- `docs/07_depth_geometry_validation.md`：深度/点云参与质检与评估的方法。
- `docs/08_open_questions.md`：需要用户确认的问题。
- `docs/09_robot_independent_capture.md`：实测机独立采集脚本设计。
- 外部 Python 项目文档：`/home/xia/桌面/colt_trainer_py/docs/`

## 当前默认路线

```text
采集数据
  -> 预处理、质检、抽帧、划分
  -> 标注 chair / chair_seat / aluminum_block mask
  -> 训练 YOLO11l-seg，必要时对比 YOLO11x-seg
  -> 用深度/点云做几何评估
  -> 导出 ONNX
  -> 生成 labels/preprocess/thresholds/model_card/metrics
  -> 复制到 colt_bridle/models/runtime/
```

第一版训练重点不是追求开放世界泛化，而是保证当前实验室、当前一种椅子多实例、一个小铝块和 Kinect2/云台/小车运动视角下稳定可用。
