# colt_bridle 开发文档

`colt_bridle` 是 Colt 系统的感知与安全接口层。名字中的 bridle 表示“缰绳”：它不直接替代底层驱动，而是在 Kinect2、云台、后续小车、机械臂和 UI 之间提供清晰、受约束、可调试的中间层。

## 职责

- 订阅 Kinect2 RGB、深度、彩色点云和 TF。
- 检测椅子、估计椅面、识别小铝块。
- 用深度/点云验证 RGB 检测结果。
- 把小铝块坐标约束到椅面局部坐标系内。
- 对坐标做历史滤波、跳变拒绝和任务状态管理。
- 发布给 RViz、导航、机械臂和 UI 使用的稳定结果。
- 规划云台观察目标，但真实云台命令必须经过安全转发器。

## 不负责

- 不训练模型。
- 不直接发布 `/cmd_vel`。
- 不直接调用机械臂抓取或放置。
- 不修改 `wpv4_objects_3d`、`wpv4_pt`、`kinect2_bridge` 的原行为。

## 文档

- `docs/01_package_architecture.md`：包结构和节点划分。
- `docs/02_technical_route.md`：椅子、椅面、小铝块、云台的技术路线。
- `docs/03_runtime_inputs_outputs.md`：运行时输入输出话题。
- `docs/04_model_training_boundary.md`：模型训练与运行包的边界。
- `docs/05_field_test_constraints.md`：从实测记录提取的工程约束。

