# colt_ui

`colt_ui` 当前只保留一个 OpenCV 椅子选择窗口。

它只负责：

1. 显示 `/colt/bridle/debug_image`
2. 读取 `/colt/bridle/detections` 里的 `chair / seat / item`
3. 鼠标选择可见椅子
4. 显示源椅、源椅面、铝块、目标椅和目标椅面的实时坐标
5. 发布 source / target 椅子 ID
6. 发布云台朝向状态 `pt_state`

## 运行

```bash
source devel/setup.bash
roslaunch colt_ui cv_selector.launch
```

输入：

```text
/colt/bridle/debug_image
/colt/bridle/detections
```

输出：

```text
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
/colt/ui/pt_state
```

## 操作

```text
鼠标左键      点选当前候选椅子
s             候选椅子设为 source，并切到 source 追踪
t             候选椅子设为 target，并保持 source 追踪
w             在 source / target 朝向状态之间切换
c             清空 source、target 和 pt_state
q             退出
```

## 当前规则

- 只允许新选择 `state=visible` 的椅子
- `source` 和 `target` 不能相同
- `pt_state=0` 表示云台朝向源椅
- `pt_state=1` 表示云台朝向目标椅
- 云台只要求当前 `pt_state` 指向的椅子已选择且可见；另一把椅子不需要同时可见
- 当前追踪椅子不可见时，云台继续扫视
- 重新选择 source 或 target 后都会先切到 `pt_state=0`，需要追踪目标椅时再按 `w`
- lost 椅子的灰框默认保留 2 秒后隐藏，可用 `lost_hide_after_sec:=秒数` 调整
