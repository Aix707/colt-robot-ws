# RViz 显示接口约定

当前阶段 `colt_msgs` 的实际用途是支持 `colt_bridle` 把输出坐标点与框显示到 RViz。推荐由 `colt_bridle/rviz_visualizer_node.py` 统一转换，不让每个算法节点各自发布 marker。

## 推荐话题

```text
/colt/bridle/markers       visualization_msgs/MarkerArray
/colt/bridle/debug_image   sensor_msgs/Image
```

## Marker 约定

### 中心点

```text
type: SPHERE
ns: center_points
frame_id: base_footprint
```

颜色建议：

```text
source_seat: green
target_seat: cyan
aluminum_block stable: red
aluminum_block candidate: yellow
stale/occluded: gray
```

### 3D 框

```text
type: CUBE 或 LINE_LIST
ns: boxes_3d
frame_id: base_footprint
```

用途：

- 椅面薄框。
- 小铝块估计尺寸框。
- 椅子粗略空间范围。

### 文字

```text
type: TEXT_VIEW_FACING
ns: labels
```

内容格式：

```text
<id> <class_name> <state>
p=<confidence>
x=<x> y=<y> z=<z>
```

### 2D 框

RViz 本身不直接显示图像 2D 框，建议两种方式：

1. 在 `/colt/bridle/debug_image` 中绘制 RGB 图像框。
2. 将 2D bbox 反投影为近似 3D 线框，仅作空间调试。

## 生命周期

marker 应设置短生命周期，避免旧结果残留：

```text
lifetime: 0.3 ~ 1.0 s
```

如果目标丢失：

- 发布 `DELETE` 或空 `MarkerArray` 清除旧 marker。
- 保留 last_known_pose 时必须以 `stale` 状态和灰色显示。

## 坐标要求

所有 marker 必须满足：

```text
header.stamp 使用检测结果时间或最近 TF 可用时间
header.frame_id 默认 base_footprint
```

如果 TF 不可用：

- 不发布 3D marker。
- 在 debug image 或 state 中报告 `tf_unavailable`。

## 与运动控制隔离

RViz 显示只用于调试，不得触发：

```text
/cmd_vel
/wpv4_pt/joint_ctrl_degree
机械臂控制话题
抓取/放置 action
```

