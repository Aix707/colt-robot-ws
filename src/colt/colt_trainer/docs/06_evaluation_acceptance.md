# 评估与验收标准

## 视觉指标

基础指标：

```text
chair mAP50
chair_seat mAP50
aluminum_block mAP50
mask mAP
precision
recall
```

小铝块优先看召回率，其次看误检率。漏检会导致无法抓取，误检会导致错误抓取，两者都危险，但第一阶段应先保证稳定识别真实目标，再用椅面约束压低误检。

## 建议通过线

第一版可上机烟测：

```text
chair_seat mask mAP50 >= 0.85
aluminum_block recall >= 0.85
aluminum_block precision >= 0.80
```

稳定版目标：

```text
chair_seat mask mAP50 >= 0.92
aluminum_block recall >= 0.92
aluminum_block precision >= 0.90
```

## 几何指标

视觉检测通过后，还要评估：

```text
椅面深度有效比例
椅面平面拟合内点比例
椅面中心多帧稳定性
小铝块坐标多帧稳定性
小铝块是否落在 seat_polygon 内
小铝块高度是否接近椅面
```

推荐通过线：

```text
椅面有效点数 >= 80
椅面平面拟合内点比例 >= 0.35
小铝块静止坐标标准差 <= 0.03 m
小铝块投影落在 seat_polygon 内比例 >= 0.95
```

## 实机前离线验证

在 rosbag 或图片序列上离线跑：

```text
ONNX 推理
椅面几何拟合
小铝块坐标计算
历史滤波
RViz marker 输出模拟
```

确认输出字段与 `colt_msgs` 设计一致。

## 实机验收

实机阶段只启动相机、云台、TF、`colt_bridle` 和 RViz。

通过标准：

- RViz 可显示椅子、椅面、小铝块中心点和框。
- 小铝块静止时坐标稳定。
- 小铝块移动时坐标连续，不出现大跳变。
- 拿走小铝块后不持续输出 `ready_for_grasp`。
- 空椅面能输出目标放置椅面。
- `/cmd_vel` 无非预期发布。
- 不触发机械臂或抓取节点。

## 运动视角专项验收

由于小车运动时观察角度变化较大，模型必须额外通过：

- 接近椅子过程中的连续视频验证。
- 云台小角度运动中的连续视频验证。
- 小铝块从远到近尺度变化验证。
- 多把同种椅子同时出现时的目标区分验证。
- 背景干扰、遮挡和运动模糊样本验证。

若静态图片指标高但运动视频中目标频繁丢失，该模型不能作为稳定版发布。

## 失败样例归档

所有失败样例应保存到：

```text
reports/failure_cases/<model_version>/
```

分类：

```text
chair_missing
seat_bad_mask
aluminum_missing
aluminum_false_positive
depth_invalid
tf_unavailable
occlusion
motion_blur
```

失败样例用于下一轮补采和重训。
