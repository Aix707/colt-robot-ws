# 标注流程

## 标注目标

标注分为三个相对独立的阶段。

全图标注：

```text
chair
```

chair ROI 标注：

```text
chair_seat
```

小铝块 ROI 标注：

```text
aluminum_block
```

其中 `chair_seat` 是关键类别，因为后续小铝块 ROI、坐标、放置点和约束区域都依赖椅面。

## 推荐流程

```text
采集 rosbag / 图片序列
  -> 预处理、质检、抽帧
  -> 在 chair_seat_v001 全图工作区标注 chair
  -> 派生并训练 chair_v001
  -> 由 chair 标注/预测生成 chair ROI
  -> 在 chair_seat_roi_v001 标注 chair_seat
  -> 训练 chair_seat_roi_v001
  -> 由 chair_seat 标注/预测生成 seat ROI
  -> 标注 aluminum_block ROI
  -> 训练 aluminum_roi_v001
  -> 导出 v001 三模型运行包做实测联调
  -> 根据失败样例补采补标后再迭代 v002
```

## 自动预标注

建议使用：

```text
GroundingDINO / YOLO 预检测
SAM 2 精细分割
人工点击/框选修正
```

训练设备性能足够时，优先使用强辅助标注模型提高标注质量。SAM 2 只用于离线标注，不作为第一版实时 ROS 节点。

用户已有 LabelMe AI 辅助标注经验，因此半自动标注链路优先兼容：

```text
LabelMe JSON
COCO instance segmentation
YOLO segmentation
```

## 标注规则

### `chair`

- 标整把可见椅子。
- 被桌子、机械臂或其他物体遮挡时，只标可见部分。
- 多把椅子分别标注为多个实例。

### `chair_seat`

- 只标可用于放置/承载小铝块的椅面区域。
- 靠背、扶手、椅腿不属于椅面。
- 如果椅面被小铝块遮挡，椅面 mask 应保持物理椅面轮廓，必要时人工补全合理边界。

### `aluminum_block`

- 只在椅面附近 ROI 图像中标小铝块可见轮廓。
- 当前小铝块只有一个，但训练集中仍按实例分割类别处理。
- 小铝块可以位于椅面任意位置，不用固定区域假设限制标注。
- 反光导致边界不明显时，以人工可判断的真实物体外轮廓为准。
- 若小铝块严重模糊或遮挡超过 60%，可标为 `ignore` 或不用于训练。

## 质检规则

每个标注样本检查：

- 类别是否正确。
- mask 是否贴合物体。
- `chair_seat` 是否可支持平面拟合。
- 小铝块 ROI 是否来自椅面附近区域。
- 小铝块预测映射回原图后是否位于椅面区域内。
- RGB 图像与深度/点云是否时间对齐。
- TF 是否可用。

## 负样本设计

必须包含：

- 空椅面。
- 椅面上有其他物体。
- 类似颜色或反光物体。
- 小铝块拿走后的同视角样本。
- 机械臂或夹爪进入画面的样本。
- 小车运动造成的模糊、斜视角、大尺度变化样本。
- 小铝块被部分遮挡但仍可判断轮廓的样本。

小铝块 ROI 负样本应保留人工确认过的空标注，不要把缺失 LabelMe JSON 静默当作空标签。

## 标注版本

标注版本命名：

```text
chair_seat_v001
chair_v001
chair_seat_roi_v001
aluminum_roi_v001
chair_v002
chair_seat_roi_v002
aluminum_roi_v002
```

每个版本必须记录：

- 数据来源 session。
- 类别定义。
- 标注人和检查人。
- 抽帧策略。
- 训练/验证/测试划分。
- 已知问题。
