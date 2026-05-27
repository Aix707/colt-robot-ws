# Colt 项目目录

`colt/` 是后续新功能的项目目录，用于承接相机、云台、导航、机械臂和 UI 的新开发。当前已经开始实测数据采集和运行时接口开发，`colt_msgs`、`colt_bridle`、`colt_ui` 已加入 catkin 工作空间。

## 推荐结构

```text
colt/
  colt_msgs/          # 统一消息接口，已作为 catkin 消息包落地
  colt_trainer/       # 离线数据、标注、训练、评估和模型导出
  colt_bridle/        # 相机/云台/椅面/小铝块感知、采集和运行时接口
  colt_ui/            # 最简终端选择器，当前只选择可见椅子 ID
  colt_bringup/       # 后续总启动入口
  colt_navigation/    # 后续小车导航策略
  colt_manipulation/  # 后续机械臂抓取和放置策略
```

## 当前开发边界

- 不修改 `iai_kinect2`、`wpv4_pt`、`wpv4_objects_3d`、`wpv4_tutorials` 等原功能包。
- 新功能先通过旁路节点订阅原话题。
- 当前阶段只做采集、实时检测和云台控制；底盘和机械臂执行后续再接入。
- 模型训练与机器人实时运行分离，训练依赖不进入实测机运行链路。

## 统一数据规范

整个 `colt` 统一维护一套对象数据，适用于 `chair / seat / item`。

数据规范：

- `id`: 全局稳定 ID
- `parent_id`:
  - `chair`: `""`
  - `seat`: 所属 `chair_id`
  - `item`: 所属 `seat_id`
- `role`:
  - `chair`: `normal / source / target`
  - `seat`: `source / target`
  - `item`: `source`
- `state`: `0 / 1 / 2`
- `confidence`: 永远是 `float`
  - `lost` 时用 `0.0`
- `stamp`: 最新状态更新时间
- `frame_id`: 当前坐标系
- `x y z`: 坐标

功能规则：

- `chair` 是全局主对象，必须使用全局稳定 `id` 维护。
- `chair` 的稳定维护基于世界坐标，当前运行时默认通过 `map <- body_link <- camera` TF 链更新。
- `chair` 默认 `role=normal`，在 `colt_ui` 中可被标记为 `source` 或 `target`。
- `seat` 必须绑定父 `chair`，仅被选为 `source` 或 `target` 的椅子需要识别和维护。
- `item` 必须绑定父 `seat`，仅被选为 `source` 的椅面需要识别和维护。

`state` 统一定义：

- `0 = lost`
- `1 = visible`
- `2 = visible_no_depth`

运行约束：

- `state=0/2` 的对象坐标会跟随当前 `state=1` 的锚点对象实时纠正，用来抵消运行中小车世界坐标的整体漂移。

## 当前重点

1. `colt_msgs`：提供检测输出需要的消息接口。
2. `colt_trainer`：离线管理数据集、预处理、标注、训练、评估、ONNX 导出和模型发布；实际训练 Python 项目在 `/home/xia/桌面/colt_trainer_py`，当前已切换为 v001 三阶段 ROI 训练与导出。
3. `colt_bridle`：只保留采集、实时检测和云台控制三项功能。
4. `colt_ui`：当前只保留可见椅子 ID 选择，后续再扩展调试和操作界面。
5. 后续再由 `colt_navigation`、`colt_manipulation` 消费 `colt_bridle` 的检测输出。

## 开发顺序

统一以 `DEVELOPMENT_FLOW.md` 为准。若某个子文档和该文件冲突，优先按 `DEVELOPMENT_FLOW.md` 执行。

## 文档审查

`DOCUMENT_REVIEW.md` 记录了当前文档审查结果、已修正问题和剩余待确认项。
