# colt_bridle 技术路线

本路线来自桌面开发记录中的 `design/01_overall_technical_route.md` 和 `design/02_safety_and_constraints.md`，并结合实测记录 `05_actual_test_record.md` 中的约束整理为 `colt_bridle` 的实际开发方案。

## 核心目标

为小车导航和机械臂抓取/放置提供稳定坐标：

- 源椅子与源椅面坐标。
- 小铝块中心与抓取位姿。
- 目标椅子与目标椅面坐标。
- 放置位姿。
- 云台观察目标和视觉状态。

## 基本原则

```text
RGB 负责识别是什么
深度图/点云负责验证是否合理和计算在哪里
TF 负责转换到 base_footprint / arm_base_link / map
历史约束负责拒绝单帧跳变
椅面约束负责提高小铝块识别稳定性
云台负责维持关键区域可见
```

## 模型路线

运行时主模型推荐：

```text
YOLO11m-seg 或 YOLO11l-seg
```

识别类别：

```text
chair
chair_seat
aluminum_block
```

模型不区分 `source_chair` 和 `target_chair`。后续由 UI 在多把椅子的检测结果中人工指定源椅和目标椅，`colt_bridle` 再绑定对应的椅面坐标和任务角色。

推荐理由：

- 实例分割能提供 mask，比 bbox 更适合椅面拟合和小铝块局部定位。
- `m/l` 规模优先准确性和稳定性，适合当前从实测验证走向正式开发。
- 最终导出 ONNX，由实测机运行时加载；训练环境与运行环境分离。

辅助工具：

```text
SAM 2
```

用途是离线辅助标注椅面和小铝块，不作为第一版实时 ROS 节点。

## 椅子与椅面识别

输入：

```text
/kinect2/qhd/image_color_rect
/kinect2/qhd/image_depth_rect
/kinect2/qhd/points
/kinect2/qhd/camera_info
/tf
```

流程：

```text
RGB 分割 chair / chair_seat
  -> 提取 mask 内点云
  -> 检查有效深度比例
  -> RANSAC 拟合椅面平面
  -> 计算 seat_center / seat_normal / seat_polygon / seat_frame
  -> 历史滤波得到稳定椅面
```

椅面必须满足：

- 法向接近 `base_footprint` 的 z 轴。
- 点云内点数足够。
- 平面尺寸接近真实椅面。
- 多帧中心位置连续。

## 小铝块识别

不在全图开放搜索小铝块，而是在椅面区域内搜索：

```text
chair_seat mask / seat_polygon
  -> 限制 aluminum_block 候选
  -> 视觉模型检测小铝块
  -> 位置必须落在 seat_frame 允许区域
  -> 与上一稳定坐标连续
```

这利用了当前任务先验：小铝块会放在椅子上，但小铝块可以位于椅面任意位置，因此运行时只约束其落在 `seat_polygon` 或椅面区域内，不假设固定点位。

当前小铝块只有一个，尺寸约直径 5 cm、高 5 cm。该尺寸只作为几何验证和高度补偿的弱先验，不作为唯一判断依据。

小铝块可能被机械臂、夹爪或椅面边缘遮挡。遮挡状态下不应立即用低质量检测覆盖稳定坐标，应进入 `ARM_OCCLUSION` 或 `REACQUIRE`，并通过云台调整视角重新确认。

## 小铝块坐标计算

铝块反光导致深度可能缺失，因此坐标采用三级策略：

1. `mask` 内有效点云中值。
2. `bbox` 中心附近有效点云中值。
3. 像素中心射线与椅面平面求交，再沿椅面法向加铝块高度补偿。

输出必须记录坐标来源：

```text
pointcloud_mask_median
pointcloud_center_window_median
ray_seat_plane_intersection
```

如果使用第 3 种兜底方法，结果必须标记为可用但置信度低于真实点云中值结果。

## 安全与稳定约束

### 坐标历史约束

```text
椅面中心最大跳变: 0.15 m/frame
小铝块最大跳变: 0.08 m/frame
连续确认帧数: 3
目标超时: 1.0 ~ 2.0 s
```

低置信度或大跳变结果不能覆盖上一稳定坐标。

### 小铝块椅面约束

```text
铝块投影必须落在 seat_polygon 内
铝块高度应在椅面上方 0.0 ~ 0.08 m
椅面边界建议内缩 0.05 m 作为安全区
mask 内有效点数建议 >= 5
```

### 机械臂遮挡约束

机械臂进入视野时进入 `ARM_OCCLUSION`：

- 冻结抓取/放置坐标。
- 不用新视觉结果覆盖稳定坐标。
- 等机械臂离开后进入 `REACQUIRE` 重新确认。

### 云台约束

```text
pan: -30 ~ +30 deg
tilt: -20 ~ +20 deg
命令频率: <= 5 Hz
单次角度增量: <= 3 deg
丢失目标时停止跟踪
```

## 任务状态

建议统一状态：

```text
searching
candidate
stable
stale
occluded
not_ready
ready_for_navigation
ready_for_grasp
ready_for_place
```

导航和机械臂只消费 `ready_*` 状态。
