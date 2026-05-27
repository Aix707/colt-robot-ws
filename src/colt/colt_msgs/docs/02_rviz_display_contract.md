# 调试显示约定

当前运行链路固定输出：

```text
/colt/bridle/detections   colt_msgs/Detection3DArray
/colt/bridle/debug_image  sensor_msgs/Image
```

`colt_bridle` 现在不再自带单独的 RViz 可视化节点。若后续需要 marker，可由独立调试节点消费同一套对象数据生成。

## 标签内容

调试显示应直接复用对象字段：

```text
<id> <object_type> <state>
role=<role> conf=<confidence>
x=<x> y=<y> z=<z>
```

## 颜色建议

- `chair`：蓝色
- `seat`：绿色
- `item`：红色
- `state=lost`：灰色
- `state=visible_no_depth`：黄色

## 坐标要求

- 所有调试显示都应直接使用对象自带 `header.stamp` 和 `header.frame_id`
- 不再额外发明一套显示状态或坐标字段

## 与控制隔离

调试显示只消费对象数据，不得触发：

```text
/cmd_vel
/wpv4_pt/joint_ctrl_degree
机械臂控制话题
抓取/放置 action
```
