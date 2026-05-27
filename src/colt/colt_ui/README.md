# colt_ui

`colt_ui` 当前只保留一个终端选择器。

它只负责：

1. 读取 `/colt/bridle/detections` 里的 `chair`
2. 发布 `source / target` 椅子 ID
3. 发布云台朝向状态 `pt_state`

另外保留一个临时 RViz 调试脚本，用来观察：

1. 所有已检测到的椅子
2. 源椅和目标椅对应的椅面
3. 源椅椅面内的 item

## 运行

```bash
source devel/setup.bash
roslaunch colt_ui terminal_selector.launch
```

输入：

```text
/colt/bridle/detections
```

输出：

```text
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
/colt/ui/pt_state
```

RViz 调试脚本：

```bash
source devel/setup.bash
rosrun colt_ui rviz_marker_publisher.py
```

输出：

```text
/colt/ui/rviz_markers
```

## 交互命令

```text
s <#|id>        选源椅，并把 pt_state 置为 0
t <#|id>        选目标椅，并把 pt_state 置为 0
swap            源椅和目标椅都已选好时，不交换椅子，只把 pt_state 置为 1
clear source
clear target
clear all
q
```

## 当前规则

- 只允许新选择 `state=visible` 的椅子
- `source` 和 `target` 不能相同
- `pt_state=0` 表示云台朝向源椅
- `pt_state=1` 表示云台朝向目标椅
- 源椅和目标椅没有同时选好前，云台继续扫视
- 重新选择或清空后，`pt_state` 会回到 `0`
