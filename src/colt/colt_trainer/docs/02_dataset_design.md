# 数据集设计

## 类别

第一版推荐训练实例分割模型，但不再把椅子和小铝块放在同一个整图模型中。

椅子/椅面模型类别为：

```text
chair
chair_seat
```

小铝块 ROI 模型类别为：

```text
aluminum_block
```

说明：

- `chair` 用于识别整把椅子，服务导航接近和目标选择。当前椅子 1 种，但场景中会有多把椅子，因此需要多实例检测。源椅和目标椅由后续 UI 人工指定，不作为模型类别。
- `chair_seat` 用于椅面平面拟合、放置区域计算和小铝块约束。
- `aluminum_block` 只在椅面附近 ROI 内识别，坐标由点云或椅面平面推导。小铝块约直径 5 cm、高 5 cm，尺寸只作为弱先验。
- `source_chair` 和 `target_chair` 由 UI 人工指定，不作为模型类别。

## 数据来源

建议收集：

```text
/kinect2/qhd/image_color_rect
/kinect2/qhd/image_depth_rect
/kinect2/qhd/points
/kinect2/qhd/camera_info
/tf
/joint_states
```

可选：

```text
/kinect2/hd/image_color_rect
/kinect2/hd/points
```

HD 只用于高质量标注和离线检查，不作为默认在线训练来源，因为实测记录中 HD 点云帧率低、负载高。

实测机采集要导出标准 session 文件夹，便于复制到 Windows 训练电脑：

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

## 场景覆盖

必须覆盖：

- 源椅子上有小铝块。
- 源椅子上没有小铝块。
- 目标椅子空椅面。
- 不同距离：近、中、远。
- 不同左右位置。
- 云台不同 pan/tilt 小角度。
- 机械臂可能遮挡前后的画面。
- 小车接近椅子过程中的视角变化。
- 小车运动造成的大角度变化、运动模糊和目标尺度变化。
- 实验室复杂背景和干扰物。
- 小铝块在椅面任意位置。
- 小铝块被机械臂、夹爪或椅面边缘部分遮挡。

建议覆盖：

- 不同光照。
- 不同椅子朝向。
- 小铝块不同姿态。
- 小铝块靠近椅面边缘和位于中心区域。
- 拿走小铝块后的负样本。

## 目录结构

建议使用 COCO/YOLO 兼容结构：

```text
datasets/
  raw/
    session_YYYYMMDD_HHMMSS/
      images/
      depth/
      points/
      camera_info/
      tf/
      meta.jsonl
  annotations/
    session_YYYYMMDD_HHMMSS/
      coco.json
      labelme/
      yolo_seg/
  prepared/
    chair_seat_v001/
      images/
        train/
        val/
        test/
      labels/
        train/
        val/
        test/
      dataset.yaml
    aluminum_roi_v001/
      images/
        train/
        val/
        test/
      labels/
        train/
        val/
        test/
      dataset.yaml
  splits/
    chair_seat_v001_split.json
    aluminum_roi_v001_split.json
```

## 预处理要求

原始 session 不能直接进入训练，必须经过预处理：

- 文件完整性检查。
- RGB、深度、点云和 TF 对齐检查。
- 模糊、过曝、过暗、深度缺失严重帧过滤。
- 抽帧和相似帧去重。
- 按 session 或场景段划分 train/val/test。
- 生成标注预览图。
- 标注后转换为 YOLO segmentation 格式。

具体流程见：

```text
/home/xia/桌面/colt_trainer_py/docs/03_preprocessing_pipeline.md
```

## 元数据字段

每帧建议记录：

```json
{
  "stamp": 1778840000.0,
  "session_id": "session_YYYYMMDD_HHMMSS",
  "image_path": "images/000001.png",
  "depth_path": "depth/000001.exr",
  "points_path": "points/000001.pcd",
  "camera_info_path": "camera_info/000001.yaml",
  "tf_available": true,
  "camera_frame": "kinect2_rgb_optical_frame",
  "base_frame": "base_footprint",
  "pt_pan_deg": 0.0,
  "pt_tilt_deg": 0.0,
  "capture_mode": "near_chair_aluminum",
  "scene_tags": ["near_chair_aluminum", "aluminum_present", "motion_base"]
}
```

## 数据量建议

第一轮可用版：

```text
chair/chair_seat 整图样本: 500+ 张
aluminum_roi 正样本: 300+ 张
aluminum_roi 负样本: 500+ 张
```

当前采用“中等数据量 v001”策略：先达到能初步识别目标的规模，再用 v001 模型辅助标注后续新增数据。

稳定版：

```text
chair/chair_seat 整图样本: 1500+ 张
aluminum_roi 正样本: 800+ 张
aluminum_roi 负样本、运动和遮挡场景: 1500+ 张
```

负样本比正样本更重要，因为小铝块反光、体积小，误检会直接影响抓取安全。

## 数据划分

按 session 划分，而不是随机按图片划分：

```text
train: 70%
val: 20%
test: 10%
```

这样可以避免同一段视频的相邻帧同时进入训练和验证，造成虚高指标。
