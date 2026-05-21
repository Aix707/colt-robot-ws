# colt_bridle 包结构与节点划分

## 目标定位

`colt_bridle` 是运行时 ROS 包，负责把相机和云台得到的原始数据转成稳定的场景语义与 3D 坐标。它输出的是“可以被后续模块消费的结果”，不是一次性实验脚本。

```text
Kinect2 / 云台 / TF
  -> colt_bridle 感知、融合、约束、调试显示
  -> colt_navigation / colt_manipulation / colt_ui
```

## 建议目录

```text
colt_bridle/
  config/
    camera_topics.yaml
    model_runtime.yaml
    safety_constraints.yaml
    task_roles.yaml
  launch/
    bridle_perception.launch
    bridle_with_pt.launch
    bridle_debug_rviz.launch
  models/
    runtime/
      v002/
        chair_seat_seg.onnx
        aluminum_roi_seg.onnx
        labels.yaml
        preprocess.yaml
        thresholds.yaml
        roi_rules.yaml
        release_manifest.json
      current -> v002
  rviz/
    bridle_debug.rviz
  scripts/
    sensor_sync_node.py
    detector_node.py
    seat_geometry_node.py
    aluminum_locator_node.py
    scene_fusion_node.py
    pt_view_planner_node.py
    safety_gate_node.py
    rviz_visualizer_node.py
  docs/
```

## 节点职责

### `sensor_sync_node.py`

订阅并同步：

```text
/kinect2/qhd/image_color_rect
/kinect2/qhd/image_depth_rect
/kinect2/qhd/points
/kinect2/qhd/camera_info
/tf
```

输出内部同步帧，保证 RGB、深度、点云和 TF 时间戳一致。第一版可以不单独发布同步帧，而由下游节点使用 `message_filters` 完成同步。

### `detector_node.py`

加载运行时 v002 双模型包，按顺序输出：

```text
chair_seat_seg.onnx: 整图 chair bbox/mask/confidence, chair_seat bbox/mask/confidence
aluminum_roi_seg.onnx: 椅面 ROI 内 aluminum_block bbox/mask/confidence
```

该节点只做视觉识别，不直接宣布目标可抓取。小铝块不在整图开放搜索，必须由椅面 ROI 约束后再识别。

### `seat_geometry_node.py`

根据椅子/椅面 mask 提取点云，拟合椅面：

```text
seat_center
seat_normal
seat_polygon
seat_frame
valid_depth_ratio
plane_inlier_ratio
```

如果椅面几何不成立，则拒绝该椅子候选。

### `aluminum_locator_node.py`

只在椅面区域内处理小铝块候选：

```text
aluminum bbox/mask
  -> mask 内点云中值
  -> bbox 中心附近点云中值
  -> 像素射线与椅面平面求交兜底
```

输出小铝块中心、抓取点和坐标计算方法。

### `scene_fusion_node.py`

融合视觉、几何、历史和任务角色：

```text
source chair / source seat
target chair / target seat
aluminum target
chair approach pose
grasp pose
place pose
```

该节点负责状态机和稳定输出，例如 `candidate`、`stable`、`stale`、`ready_for_grasp`。

### `pt_view_planner_node.py`

根据任务阶段规划云台观察目标：

```text
SEARCH_CHAIR
APPROACH_CHAIR
PRE_GRASP
ARM_OCCLUSION
REACQUIRE
PLACE
```

该节点只发布期望观察方向或期望云台角，不直接写 `/wpv4_pt/joint_ctrl_degree`。

### `safety_gate_node.py`

统一做安全过滤：

- 坐标跳变拒绝。
- 椅面约束检查。
- TF 过期检查。
- 云台限幅限速。
- 机械臂遮挡期间冻结抓取/放置坐标。

### `rviz_visualizer_node.py`

把 `colt_msgs` 的检测结果转换成 RViz 可见内容：

```text
/colt/bridle/markers
/colt/bridle/debug_image
```

当前阶段的主要目标就是把输出坐标点与框稳定显示在 RViz 中。
