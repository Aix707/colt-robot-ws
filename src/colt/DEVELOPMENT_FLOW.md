# Colt 开发顺序与流程

本文档是当前 Colt 相机、云台、椅面、小铝块感知系统的开发顺序基准。后续如果修改路线，优先更新本文件，再同步各子模块文档。

## 总原则

- 先接口和数据，后模型和运行时，最后接运动执行。
- 训练和运行分离：`colt_trainer_py` 在 Windows CUDA 电脑训练，`colt_bridle` 在实测机运行。
- 实测机采集必须独立、可重复，不依赖训练环境。
- UI 负责人工指定源椅和目标椅，模型不训练 `source_chair` 或 `target_chair`。
- 椅子/椅面识别先完成，小铝块识别后完成；两类模型相对独立。
- 小铝块模型只在椅面附近 ROI 内运行，不在整图开放搜索。
- 小铝块可以在椅面任意位置，因此训练和运行都不能假设固定放置点，只能约束其位于椅面内。
- 小铝块可能被机械臂、夹爪或椅面边缘遮挡；遮挡时优先通过云台换视角和历史稳定坐标处理。
- 新开发使用 `/colt/bridle/*`，历史 `/kinect_pt_test/*` 只保留为测试记录。
- 在导航和机械臂接入前，所有输出只做 RViz、echo 和规划预览，不触发真实运动。
- 运行时默认使用 ROS Noetic Python3 + `onnxruntime`；TensorRT/OpenVINO 作为后续性能优化路径。
- 半自动标注优先兼容 LabelMe JSON、COCO、YOLO segmentation。

## 阶段 0：接口冻结

目标：

- 明确 `colt_msgs` 最小消息集。
- 明确 `/colt/bridle/*` 话题。
- 明确 RViz marker 显示规则。

产物：

```text
colt_msgs/msg/Box2D.msg
colt_msgs/msg/Box3D.msg
colt_msgs/msg/Detection3D.msg
colt_msgs/msg/Detection3DArray.msg
colt_msgs/msg/Seat.msg
colt_msgs/msg/PerceptionState.msg
```

验收：

- `catkin_make` 能通过。
- `catkin_make` 后消息可正常生成。
- RViz marker 规则在 `colt_msgs` 文档中明确。

## 阶段 1：实测机独立采集

目标：

- 实现 `colt_capture_session.py`。
- 只采集 RGB、depth、points、camera_info、TF、云台状态。
- 输出 Windows 可读标准 session 文件夹。

输入：

```text
/kinect2/qhd/image_color_rect
/kinect2/qhd/image_depth_rect
/kinect2/qhd/points
/kinect2/qhd/camera_info
/tf
/joint_states
/wpv4_pt/raw_joint_states
```

输出：

```text
session_YYYYMMDD_HHMMSS/
  images/
  depth/
  points/
  camera_info/
  tf/
  preview/
  meta.jsonl
  session.yaml
```

验收：

- 不发布 `/cmd_vel`。
- 不调用机械臂或抓取节点。
- 采集文件能直接复制到 `colt_trainer_py/datasets/raw/`。
- 抽样帧能在 Windows 上打开并通过预处理脚本读取。

## 阶段 2：预处理管线

目标：

- 在 `colt_trainer_py` 中实现 `prepare_dataset.py`。
- 完成 session 校验、抽帧、质量过滤、划分和格式转换。

处理：

```text
raw session
  -> 文件完整性检查
  -> RGB/depth/points/TF 对齐检查
  -> 模糊/曝光/depth 有效比例过滤
  -> 抽帧去重
  -> 按 session 或场景段划分 train/val/test
  -> 输出待标注数据
```

验收：

- 能处理至少一个完整实测 session。
- 输出 `datasets/interim/` 和 `datasets/prepared/`。
- 不把同一连续片段随机打散到 train 和 val。

## 阶段 3：辅助标注与数据集 v001

目标：

- 用强辅助模型预标注，再人工修正。
- 先形成 `chair_seat_v001`，用于初步识别椅子和椅面。
- 再由椅面结果生成 `aluminum_roi_v001`，只在椅面附近 ROI 标注小铝块。

椅子/椅面类别：

```text
chair
chair_seat
```

小铝块 ROI 类别：

```text
aluminum_block
```

注意：

- 不标 `source_chair`、`target_chair` 类别。
- 小铝块尺寸约直径 5 cm、高 5 cm，只作为弱先验。
- 小铝块训练样本来自椅面附近 ROI，负样本必须包含空椅面、反光干扰物、运动模糊、机械臂/夹爪遮挡。
- v001 数据量采用中等规模，目标是先训练出能初步识别目标的模型；后续用 v001 模型加速更多数据的半自动标注。
- `v001` 不作为实机正式运行模型，`v002` 才是实际在线运行版本。

验收：

- 椅子/椅面标注可转换为 YOLO segmentation。
- 小铝块 ROI 标注可转换为独立 YOLO segmentation 数据集。
- `chair_seat` mask 能支持椅面平面拟合。
- 标注版本、session 来源、划分文件完整。

## 阶段 4：训练、迭代与 v002 导出

目标：

- 在 Windows CUDA 电脑上训练。
- 默认训练 `YOLO11l-seg`，必要时对比 `YOLO11x-seg`。
- 先训练椅子/椅面模型，再训练小铝块 ROI 模型。
- 用 v001 辅助补采和补标，迭代得到 v002。
- 导出 v002 双模型 ONNX 和运行时配置。

命令入口：

```powershell
python scripts/train_seg.py --config configs/train_chair_seat_v001.yaml
python scripts/extract_aluminum_roi.py --config configs/aluminum_roi.yaml
python scripts/train_seg.py --config configs/train_aluminum_roi_v001.yaml
python scripts/train_seg.py --config configs/train_chair_seat_v002.yaml
python scripts/train_seg.py --config configs/train_aluminum_roi_v002.yaml
python scripts/export_runtime.py --config configs/export_runtime_v002.yaml
```

输出：

```text
exports/colt_runtime_v002/runtime/
  chair_seat_seg.onnx
  aluminum_roi_seg.onnx
  labels.yaml
  preprocess.yaml
  thresholds.yaml
  roi_rules.yaml
  metrics.json
  model_card.md
  release_manifest.json
```

验收：

- 测试集视觉指标达到烟测线。
- ONNX 推理结果与训练框架结果一致。
- 运行时配置包含椅面 ROI 规则、小铝块弱尺寸先验和阈值。
- v002 是后续实机 detector 默认加载版本。

## 阶段 5：离线几何评估

目标：

- 在 `colt_trainer_py` 中对模型输出做深度/点云几何评估。
- 验证模型输出是否能形成稳定 3D 坐标。

检查：

```text
椅面平面拟合成功率
椅面法向合理性
小铝块投影是否落在 seat_polygon 内
小铝块坐标多帧稳定性
射线与椅面求交兜底比例
```

验收：

- 几何指标通过。
- 失败样例已归档。
- 运行阈值可写入 `thresholds.yaml`。

## 阶段 6：colt_bridle 离线回放

目标：

- 在开发机或实测机上用保存的 session/rosbag 回放测试 `colt_bridle`。
- 不依赖实时硬件、不控制云台。

实现节点：

```text
detector_node.py
seat_geometry_node.py
aluminum_locator_node.py
scene_fusion_node.py
rviz_visualizer_node.py
```

验收：

- `/colt/bridle/detections` 输出完整。
- `/colt/bridle/markers` 能在 RViz 显示椅子、椅面、小铝块点和框。
- 坐标来源和状态字段完整。

## 阶段 7：实机静态在线验证

目标：

- 只启动相机、云台、TF、`colt_bridle`、RViz。
- 验证静态椅子、椅面、小铝块识别与坐标稳定性。

禁止：

- 不发布 `/cmd_vel`。
- 不调用机械臂。
- 不控制真实云台跟踪。

验收：

- TF 稳定。
- QHD 输入稳定。
- 小铝块静止坐标稳定。
- 拿走小铝块后不输出 `ready_for_grasp`。

## 阶段 8：UI 指定源椅和目标椅

目标：

- UI 在检测到的多把椅子中人工指定源椅和目标椅。
- `colt_bridle` 根据 UI 选择绑定 `source_seat_pose` 和 `target_seat_pose`。

临时接口：

```text
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
```

验收：

- 选中源椅后，源椅面和小铝块绑定正确。
- 选中目标椅后，放置点位于目标椅面内。
- UI 切换选择时不会留下旧 marker 或旧坐标。

## 阶段 9：云台视角辅助

目标：

- 实现云台观察规划和限幅转发器。
- 第一版云台只允许在零位附近 `±15°` 范围内运动。

流程：

```text
pt_view_planner_node.py
  -> /colt/bridle/pt_view_goal
  -> pt_limited_forwarder_node.py
  -> /wpv4_pt/joint_ctrl_degree
```

验收：

- 丢失目标时停止跟踪。
- 云台运动时坐标使用正确时间戳 TF。
- 机械臂遮挡时冻结抓取/放置坐标或进入 `REACQUIRE`。

## 阶段 10：导航与机械臂规划预览

目标：

- 只做接口联调和规划预览，不执行真实底盘/机械臂动作。

输出：

```text
/colt/bridle/chair_approach_pose
/colt/bridle/grasp_pose
/colt/bridle/place_pose
```

验收：

- 导航目标位于椅子前方操作位。
- 抓取点位于源椅面小铝块附近。
- 放置点位于目标椅面内。
- 未达到 `ready_*` 状态时，下游不执行。

## 第一轮推荐执行顺序

```text
1. 实现 colt_msgs
2. 实现实测机独立采集脚本
3. 采集中等数据量完整 session
4. 实现 colt_trainer_py 预处理
5. 完成 chair_seat_v001 辅助标注
6. 训练 chair_seat_v001，生成 aluminum_roi_v001 数据
7. 训练 aluminum_roi_v001
8. 用 v001 辅助补采和补标，迭代 chair_seat_v002 与 aluminum_roi_v002
9. 做离线几何评估并导出 runtime/v002
10. 实现 colt_bridle 最小在线链路
11. 实机静态验证
12. 再开发 UI 选择、云台辅助、导航/机械臂预览
```
