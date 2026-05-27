# colt_msgs

`colt_msgs` 定义 Colt 当前统一对象数据接口。

运行链路当前实际使用：

```text
msg/Box2D.msg
msg/Detection3D.msg
msg/Detection3DArray.msg
```

## 统一对象字段

`Detection3D.msg` 统一表达 `chair / seat / item`：

```text
header
id
parent_id
object_type
role
state
confidence
x
y
z
bbox
```

字段约束：

- `id`：稳定对象 ID
- `parent_id`：`chair=""`，`seat -> chair`，`item -> seat`
- `object_type`：`chair / seat / item`
- `role`：`chair=normal/source/target`，`seat=source/target`，`item=source`
- `state`：`0=lost`，`1=visible`，`2=visible_no_depth`
- `confidence`：永远是 `float`，`lost` 时用 `0.0`
- `header.stamp`：最新状态更新时间
- `header.frame_id`：当前坐标系
- `x y z`：当前对象坐标

## 当前边界

- 不定义底盘控制命令。
- 不定义机械臂执行 action。
- 不定义 UI 交互协议。
- `colt_ui` 只消费对象数据并发布 source/target 椅子 ID。

## 文档

- `docs/01_message_design.md`：当前消息结构。
- `docs/02_rviz_display_contract.md`：调试显示约定。

## 烟测

```bash
cd /home/xia/桌面/catkin_ws
catkin_make
source devel/setup.bash
rosmsg show colt_msgs/Detection3D
```
