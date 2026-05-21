# 深度与点云几何验证

## 目的

`colt_trainer` 不只训练 RGB 模型，还要用深度图和点云评估模型输出是否能服务机器人任务。最终目标不是“图像上看起来识别对了”，而是“坐标能用于导航、抓取和放置”。

## 离线验证输入

```text
RGB 图像
depth 图
PointCloud2 或导出的 PCD/NPY
camera_info
TF
模型预测 mask/bbox
人工标注 mask/bbox
```

## 椅面验证

对 `chair_seat` mask：

```text
提取 mask 内点云
  -> 去除无效点
  -> RANSAC 拟合平面
  -> 计算法向、中心、面积、内点比例
  -> 与人工标注/历史结果比较
```

记录指标：

```text
depth_valid_ratio
plane_inlier_ratio
seat_center_xyz
seat_normal
seat_polygon_area
fit_success
```

## 小铝块验证

对 `aluminum_block` mask：

```text
mask 内点云中值
bbox 中心窗口点云中值
像素射线与椅面平面求交
```

比较三种坐标来源：

```text
pointcloud_mask_median
pointcloud_center_window_median
ray_seat_plane_intersection
```

如果小铝块深度缺失严重，但椅面平面稳定，则允许使用射线与椅面求交作为运行时兜底。

## 任务约束验证

每个预测必须检查：

- 小铝块投影是否在椅面 polygon 内。
- 小铝块高度是否在椅面上方合理范围。
- 与上一帧稳定坐标的距离是否连续。
- 椅面中心是否稳定。
- 机械臂遮挡样本中是否会误输出 ready 状态。

## 输出报告

建议生成：

```text
reports/geometry_eval/<model_version>/geometry_metrics.json
reports/geometry_eval/<model_version>/bad_cases/
```

`geometry_metrics.json` 示例：

```json
{
  "seat_fit_success_rate": 0.93,
  "seat_mean_depth_valid_ratio": 0.68,
  "seat_mean_plane_inlier_ratio": 0.51,
  "aluminum_inside_seat_rate": 0.96,
  "aluminum_coordinate_std_m": 0.024,
  "ray_plane_fallback_rate": 0.37
}
```

## 与 colt_bridle 的关系

`colt_trainer` 的几何验证报告用于确定 `colt_bridle` 的运行阈值：

```text
thresholds.yaml
runtime_constraints.yaml
history_filter 参数
坐标兜底策略
```

训练指标好但几何指标差的模型不能发布。
