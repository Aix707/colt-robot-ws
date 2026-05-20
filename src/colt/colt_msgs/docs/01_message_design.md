# colt_msgs 消息设计

## 设计原则

- 每个坐标必须带 `Header`。
- 坐标默认使用 `base_footprint`，后续可转换到 `arm_base_link`、`map` 或 `seat_frame`。
- bbox 与 3D 坐标同时保留，方便 RViz、UI 和算法调试。
- 状态字段必须显式表达结果是否可用于导航、抓取或放置。
- 当前阶段只服务感知显示和调试，不触发运动执行。

## 第一阶段建议消息

### `Box2D.msg`

```text
int32 xmin
int32 ymin
int32 xmax
int32 ymax
float32 confidence
string class_name
```

### `Box3D.msg`

```text
geometry_msgs/Point center
geometry_msgs/Vector3 size
geometry_msgs/Quaternion orientation
float32 confidence
string class_name
```

说明：

- `center` 与 `orientation` 所属坐标系由外层 `Header` 决定。
- 椅面可以先用薄 3D box 表示，后续再增加 polygon。

### `Detection3D.msg`

```text
std_msgs/Header header
string id
string class_name
string role
string state
float32 confidence

Box2D bbox
Box3D box
geometry_msgs/PoseStamped pose

string coordinate_method
bool depth_valid
bool geometry_constraint_passed
bool history_constraint_passed
```

字段说明：

```text
role:
  source_chair
  target_chair
  source_seat
  target_seat
  aluminum_block

state:
  searching
  candidate
  stable
  stale
  occluded
  not_ready
  ready_for_navigation
  ready_for_grasp
  ready_for_place

coordinate_method:
  pointcloud_mask_median
  pointcloud_center_window_median
  ray_seat_plane_intersection
  seat_plane_fit
  model_only
```

### `Detection3DArray.msg`

```text
std_msgs/Header header
Detection3D[] detections
string scene_state
```

### `Seat.msg`

```text
std_msgs/Header header
string id
string role
string state
geometry_msgs/PoseStamped pose
geometry_msgs/Vector3 normal
geometry_msgs/Point[] polygon
float32 plane_inlier_ratio
float32 depth_valid_ratio
bool geometry_constraint_passed
bool history_constraint_passed
```

### `PerceptionState.msg`

```text
std_msgs/Header header
string state
string active_task
string detail
bool ready_for_navigation
bool ready_for_grasp
bool ready_for_place
```

## 兼容策略

在 `colt_msgs` 真正加入 `package.xml` 并编译前，`colt_bridle` 可以先用：

```text
std_msgs/String(JSON)
geometry_msgs/PoseStamped
visualization_msgs/MarkerArray
```

但 JSON 字段应尽量与上面的消息设计一致，方便后续平滑迁移。

