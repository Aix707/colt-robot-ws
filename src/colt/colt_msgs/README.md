# colt_msgs 开发文档

`colt_msgs` 用于定义 Colt 系统内部的稳定数据接口。当前阶段的重点不是直接驱动小车或机械臂，而是把感知输出的坐标点、2D 框、3D 框、类别、置信度和状态表达清楚，并能由 `colt_bridle` 转换成 RViz 可见的 marker。

## 当前阶段范围

先支持 RViz 调试显示：

```text
检测目标中心点
2D bbox
3D box 或椅面 polygon
类别名称
置信度
状态
坐标系和时间戳
```

当前不定义：

- 底盘控制命令。
- 机械臂执行 action。
- UI 操作协议。

这些内容等感知输出稳定后，再由 `colt_navigation`、`colt_manipulation`、`colt_ui` 各自扩展。

## 文档

- `docs/01_message_design.md`：消息设计建议。
- `docs/02_rviz_display_contract.md`：RViz 显示约定。

