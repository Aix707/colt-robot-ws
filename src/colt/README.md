# Colt 项目目录

`colt/` 是后续新功能的项目目录，用于承接相机、云台、导航、机械臂和 UI 的新开发。当前已经开始实测数据采集和运行时接口开发，`colt_msgs`、`colt_bridle`、`colt_ui` 已加入 catkin 工作空间。

## 推荐结构

```text
colt/
  colt_msgs/          # 统一消息接口，已作为 catkin 消息包落地
  colt_trainer/       # 离线数据、标注、训练、评估和模型导出
  colt_bridle/        # 相机/云台/椅面/小铝块感知、采集和运行时接口
  colt_ui/            # 最简操作界面，当前只选择源椅和目标椅
  colt_bringup/       # 后续总启动入口
  colt_navigation/    # 后续小车导航策略
  colt_manipulation/  # 后续机械臂抓取和放置策略
```

## 当前开发边界

- 不修改 `iai_kinect2`、`wpv4_pt`、`wpv4_objects_3d`、`wpv4_tutorials` 等原功能包。
- 新功能先通过旁路节点订阅原话题。
- 当前阶段只定义感知、坐标、框和 RViz 调试输出；底盘和机械臂执行后续再接入。
- 模型训练与机器人实时运行分离，训练依赖不进入实测机运行链路。

## 当前重点

1. `colt_msgs`：先定义能表达坐标点、2D 框、3D 框、类别、置信度、状态的接口，并约定如何转换成 RViz marker；当前已实现第一阶段消息文件。
2. `colt_trainer`：离线管理数据集、预处理、标注、训练、评估、ONNX 导出和模型发布；实际训练 Python 项目在 `/home/xia/桌面/colt_trainer_py`。
3. `colt_bridle`：实现椅子/椅面/小铝块识别、RGB 与深度/点云交叉验证、历史滤波和云台视角辅助。
4. `colt_ui`：先提供源椅/目标椅选择，后续再扩展调试和操作界面。
5. 后续再由 `colt_navigation`、`colt_manipulation` 消费 `colt_bridle` 的稳定输出。

## 开发顺序

统一以 `DEVELOPMENT_FLOW.md` 为准。若某个子文档和该文件冲突，优先按 `DEVELOPMENT_FLOW.md` 执行。

## 文档审查

`DOCUMENT_REVIEW.md` 记录了当前文档审查结果、已修正问题和剩余待确认项。
