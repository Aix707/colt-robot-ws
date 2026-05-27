# colt_msgs 消息设计

当前主链路只围绕统一对象数据：

```text
Box2D
Detection3D
Detection3DArray
```

## `Detection3D.msg`

```text
std_msgs/Header header

uint8 STATE_LOST=0
uint8 STATE_VISIBLE=1
uint8 STATE_VISIBLE_NO_DEPTH=2

string id
string parent_id
string object_type
string role
uint8 state
float32 confidence
float32 x
float32 y
float32 z

Box2D bbox
```

字段说明：

- `header.stamp`：对象最新状态更新时间
- `header.frame_id`：当前坐标系
- `id`：稳定对象 ID
- `parent_id`：
  - `chair`: `""`
  - `seat`: 所属 `chair.id`
  - `item`: 所属 `seat.id`
- `object_type`：`chair / seat / item`
- `role`：
  - `chair`: `normal / source / target`
  - `seat`: `source / target`
  - `item`: `source`
- `state`：
  - `0 = lost`
  - `1 = visible`
  - `2 = visible_no_depth`
- `confidence`：永远是 `float`，`lost` 时为 `0.0`
- `x y z`：当前对象坐标
- `bbox`：当前图像框，给 UI 和云台控制复用

## `Detection3DArray.msg`

```text
std_msgs/Header header
colt_msgs/Detection3D[] detections
string scene_state
```

字段说明：

- `header`：本帧检测输出时间和默认坐标系
- `detections`：本帧所有 `chair / seat / item`
- `scene_state`：当前检测流状态，现阶段只使用 `active / empty`

## 当前边界

- `chair` 是全局主对象，必须使用稳定 `id` 维护。
- `seat` 必须绑定父 `chair`，仅 `source / target` 椅子需要识别和维护。
- `item` 必须绑定父 `seat`，仅 `source` 椅面需要识别和维护。
