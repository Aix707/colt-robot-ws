# AGENTS.md

本文件是 `/home/xia/桌面/catkin_ws` 的 Codex 自动开发、review、Git 与 PR 总规范。适用于整个仓库；若后续某个子目录新增更具体的 `AGENTS.md`，以更靠近被修改文件的规范为准。

## 项目目标与技术栈

本仓库是一个 ROS/catkin 工作空间，远端仓库为 `Aix707/colt-robot-ws`。现有代码包含 WPV4 小车、WPM2 机械臂、Kinect2、云台、导航、点云检测、RViz 显示和第三方驱动/工具包。

当前新开发集中在 `src/colt/`，目标是为“小车导航 + 机械臂抓取/放置”提供稳定、可调试、受安全约束的椅子、椅面和小铝块感知结果。

实际技术栈以仓库现状为准：

- ROS Noetic / catkin 工作空间，常规构建命令为 `catkin_make`。
- 现有运行包主要是 C++ ROS 节点，使用 `roscpp`、`rospy`、TF、PCL、OpenCV、RViz、MoveIt、message generation。
- Kinect2 由 `src/iai_kinect2` 提供，主要话题包含 `/kinect2/qhd/image_color_rect`、`/kinect2/qhd/image_depth_rect`、`/kinect2/qhd/points`、`/kinect2/qhd/camera_info`。
- 云台由 `wpv4_bringup/wpv4_pt` 控制，命令话题为 `/wpv4_pt/joint_ctrl_degree`，反馈经 `/joint_states` 或实测约定的 `/wpv4_pt/raw_joint_states` 接入。
- 新模型训练不在本仓库内完成。外部训练项目位于 `/home/xia/桌面/colt_trainer_py`，用于 Windows CUDA 电脑上的预处理、辅助标注、训练、评估和 ONNX 导出。

## 当前功能范围

当前 `src/colt/` 正在从文档设计进入可编译 ROS 包开发。`colt_msgs` 和 `colt_bridle` 已开始落地为 catkin 包；其他规划目录仍不能假装已经存在运行节点。

当前确定的新功能范围：

- `colt_msgs`：提供稳定消息接口，表达 2D 框、3D 框、坐标点、类别、置信度、状态，并支持 RViz marker 显示。
- `colt_trainer`：作为离线训练设计入口，约定数据采集、预处理、标注、训练、评估和模型导出；真实训练代码在外部 `colt_trainer_py`。
- `colt_bridle`：运行时感知与安全约束层，当前只包含 RViz 假场景烟测节点；未来负责椅子/椅面/小铝块识别、RGB 与深度/点云融合、TF 坐标转换、历史滤波、安全状态和 RViz 输出。
- 后续 `colt_navigation`、`colt_manipulation`、`colt_ui` 尚未创建，只有目录规划，不能在代码中假设它们已经存在。

现有旧功能包只作为输入、参考或底层能力使用：

- `iai_kinect2`：相机驱动、图像、深度图、点云和 viewer。
- `wpv4_bringup`：底盘、IMU、云台、URDF、TF 和 bringup。
- `wpv4_behaviors`：旧 3D 物体检测、抓取相关节点；`wpv4_objects_3d` 在复杂实验室和小铝块上不稳定，不能作为新链路主检测算法。
- `wpv4_tutorials`：教程和 demo，其中 `move_pt_demo` 会同时发布 `/wpv4_pt/joint_ctrl_degree` 和 `/cmd_vel`，不能作为安全云台追踪主流程直接使用。

## 目录结构说明

- `src/colt/README.md`：Colt 总目录说明和当前开发边界。
- `src/colt/DEVELOPMENT_FLOW.md`：权威开发顺序。若其他文档冲突，先按此文件执行并同步修正文档。
- `src/colt/DOCUMENT_REVIEW.md`：文档审查记录、已确认决策和非阻塞记录项。
- `src/colt/colt_msgs/`：消息和 RViz 显示接口设计文档。
- `src/colt/colt_trainer/`：离线训练设计文档和配置模板，不包含真实训练数据。
- `src/colt/colt_bridle/`：运行时感知、安全约束和接口设计文档。
- `THIRD_PARTY_SOURCES.md`：记录已吸收到主仓库的第三方包来源。
- `.gitignore`：忽略 `build/`、`devel/`、模型、rosbag、点云、数据集、训练输出和 IDE 文件。

不要把 `/home/xia/桌面/colt_trainer_py` 当成本仓库的一部分提交；它是外部可打包训练项目。

## 开发顺序

必须遵守 `src/colt/DEVELOPMENT_FLOW.md` 的阶段顺序。当前推荐顺序是：

1. 实现 `colt_msgs`，并用假数据在 RViz 显示点、框和文字。
2. 实现实测机独立采集脚本，采集 RGB、depth、points、camera_info、TF 和云台状态，不发布运动命令。
3. 采集中等数据量完整 session。
4. 在外部 `colt_trainer_py` 中实现预处理、质检、抽帧和划分。
5. 形成 `chair_aluminum_v001` 标注数据集。
6. 在 Windows CUDA 电脑训练默认 `YOLO11l-seg`，必要时用 `YOLO11x-seg` 做上限对比。
7. 做离线几何评估，确认椅面和小铝块 3D 坐标可用。
8. 实现 `colt_bridle` 最小在线链路。
9. 实机静态验证。
10. 用 v001 模型辅助补采和补标，迭代 v002。
11. 再开发 UI 选择、云台辅助、导航和机械臂规划预览。

禁止跳过接口、假数据 RViz、离线验证，直接接入底盘或机械臂真实运动。

## 强制开发规则

以下规则是强制性的：

- 单功能：每次任务只实现一个清晰功能或一个小修复，不把消息定义、采集、训练、推理、UI、导航和机械臂控制混在同一个改动中。
- 小步提交：每个 commit 必须小而可审查；一个 commit 只表达一个目的。
- 测试优先：改动前先确认可执行的验证方式；实现后必须运行相应本地测试或给出无法运行的明确原因。
- PR 审查后合并：不得直接向 `main` 推送功能改动；功能分支必须通过 PR，审查后再合并。

## Codex 每次执行任务的步骤

每次开始任务时：

1. 读取本文件，以及被修改目录附近的 README、docs、CMake/package 配置。
2. 运行 `git status --short --branch`，确认当前分支和未提交改动。
3. 判断任务属于文档、消息接口、采集、训练、运行时、RViz、云台、导航、机械臂还是 Git/PR 流程。
4. 先搜索再修改，优先使用 `rg` 和 `rg --files`。
5. 明确输入、输出、话题、消息类型、坐标系、状态字段和安全边界。
6. 只编辑完成当前任务所需的最小文件集合。
7. 对现有第三方/原项目源码保持克制，不做无关格式化、重排、重命名或风格统一。
8. 实现后运行可用测试，并检查 `git diff`。
9. 总结改动、测试结果、未验证项和后续建议。

如果涉及真实硬件或运动：

- 先确认是否会发布 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree`、机械臂控制话题或抓取 action。
- 默认只允许相机、云台状态、TF、RViz 和旁路感知输出。
- 真实运动相关命令必须有安全限幅、停止条件和人工确认，不得由感知节点直接发布。

## 本地测试与 review 流程

根据改动范围选择测试，不要编造不存在的测试命令。

通用检查：

```bash
git status --short --branch
git diff --check
```

ROS 工作空间构建检查：

```bash
catkin_make
```

只改文档时，可以不运行 `catkin_make`，但必须说明未运行原因。

新增或修改 ROS 消息、CMake、package 配置时，必须运行 `catkin_make`。若环境缺少 ROS 依赖导致失败，要记录失败命令、错误摘要和下一步依赖处理建议。

新增 Python 脚本时，至少运行语法检查：

```bash
python3 -m py_compile <script.py>
```

如果脚本依赖 ROS 环境或硬件话题，不能在线完整运行时，应补充离线假数据或 dry-run 参数；没有 dry-run 时必须在 PR 中说明测试缺口。

外部训练项目 `/home/xia/桌面/colt_trainer_py` 的命令存在于该外部目录，不属于本仓库 CI。涉及训练文档或训练脚本时，先进入外部目录检查对应脚本，再执行：

```bash
python scripts/prepare_dataset.py --config configs/preprocess.yaml
python scripts/auto_annotate.py --config configs/auto_annotation.yaml
python scripts/train_seg.py --config configs/train_yolo_seg.yaml
python scripts/evaluate_geometry.py --config configs/geometry_eval.yaml
python scripts/export_runtime.py --config configs/export_runtime.yaml
```

执行前必须确认这些脚本当前实现是否只是占位，不能把文档目标命令当作已经验证通过的事实。

review 时优先检查：

- 是否破坏现有 ROS 包编译。
- 是否修改了原功能包行为。
- 是否引入未受控运动输出。
- 是否缺失 `Header`、`frame_id`、时间戳或 TF 检查。
- 是否把训练数据、模型权重、rosbag、点云大文件提交进仓库。
- 是否有未解释的测试缺口。

## Git 分支、commit、push、PR 规范

主分支：

- `main` 只保存已审查、可追溯的稳定改动。
- 不直接在 `main` 上做功能开发。

分支命名：

- `feature/<short-topic>`：新功能。
- `fix/<short-topic>`：修复。
- `docs/<short-topic>`：文档。
- `test/<short-topic>`：测试或验证工具。

推荐流程：

```bash
git checkout main
git pull --ff-only
git checkout -b feature/<short-topic>
```

提交前：

```bash
git status --short
git diff
git diff --check
```

commit 规则：

- 每次提交只包含一个功能或修复。
- commit message 使用简短祈使句，例如 `Add colt_msgs detection messages`。
- 不提交 `build/`、`devel/`、数据集、模型、rosbag、点云和临时日志。
- 不把外部 `/home/xia/桌面/colt_trainer_py` 内容混进本仓库，除非另有明确迁移任务。

push 和 PR：

```bash
git push -u origin <branch>
gh pr create --base main --head <branch> --title "<title>" --body "<summary>"
```

PR 描述必须包含：

- 改动摘要。
- 测试命令和结果。
- 是否影响相机、云台、底盘、机械臂或 UI。
- 是否新增/修改 ROS 话题、消息、launch、配置或模型产物。
- 已知风险和未验证项。

合并要求：

- PR 审查通过后再合并。
- 合并前确认分支与 `main` 无冲突。
- 不使用 `git push --force` 覆盖他人工作；确需改写历史时必须先得到明确许可。

## 禁止事项

禁止以下行为：

- 在没有明确任务和安全约束时发布 `/cmd_vel`。
- 让感知节点直接发布 `/wpv4_pt/joint_ctrl_degree`；云台真实命令必须经过安全转发器。
- 启动抓取、机械臂或底盘运动链路作为感知开发的默认测试。
- 把 `wpv4_objects_3d` 当作小铝块正式识别主链路。
- 在 `colt_bridle` 中引入 PyTorch、SAM 2 或完整训练依赖。
- 把训练集原图、标注工程、rosbag、PCD/PLY、大型 NPY/NPZ、ONNX/PT/PTH/engine/weights 默认提交到 Git。
- 无关修改第三方包或原项目包，尤其是 `iai_kinect2`、`wpv4_bringup`、`wpv4_behaviors`、`wpv4_tutorials`、`wpm2_*`。
- 运行会批量重写第三方源码的格式化工具。
- 输出没有 `header.stamp`、`header.frame_id` 或坐标系说明的坐标。
- 用单帧低置信度结果覆盖稳定坐标。
- 遮挡状态下更新抓取点或放置点。
- 把文档中的规划目录、规划节点或规划命令说成已经实现。

## 完成标准

一个任务完成时必须满足：

- 改动范围只覆盖当前任务。
- 文档、代码和配置互相一致；如果发现文档冲突，优先更新 `src/colt/DEVELOPMENT_FLOW.md` 或在总结中明确指出。
- 新增接口包含话题名、消息类型、坐标系、时间戳要求和状态语义。
- 涉及运行时感知时，必须有 RViz 或 echo 可验证输出。
- 涉及坐标时，必须说明坐标来源，例如点云中值、中心窗口点云中值或射线与椅面平面求交。
- 涉及安全时，必须说明限幅、停止条件、超时、历史约束和禁止输出。
- 本地测试已运行并记录结果；无法运行时说明原因。
- `git status --short` 中只剩当前任务相关改动。

## PR 检查清单

提交 PR 前逐项检查：

- [ ] 这个 PR 只解决一个功能、修复或文档目标。
- [ ] 已阅读并遵守本 `AGENTS.md`。
- [ ] 已确认是否影响 `colt_msgs`、`colt_trainer`、`colt_bridle` 或旧功能包。
- [ ] 已运行适用测试：`catkin_make`、`python3 -m py_compile`、离线假数据测试或文档检查。
- [ ] PR 描述包含测试命令和结果。
- [ ] 没有提交 `build/`、`devel/`、rosbag、模型权重、点云、数据集或训练输出。
- [ ] 没有无关格式化第三方/原项目源码。
- [ ] 没有新增未受控的 `/cmd_vel`、`/wpv4_pt/joint_ctrl_degree` 或机械臂控制发布者。
- [ ] 所有坐标输出都有 `frame_id` 和时间戳要求。
- [ ] RViz marker 不会触发运动控制。
- [ ] 若涉及模型发布，包含模型卡、指标、阈值、失败样例说明和回滚路径。
- [ ] 已列出未验证项和后续实机验证计划。

## 信息不足时的处理方式

Codex 遇到信息不足时按以下顺序处理：

1. 先查仓库：README、docs、launch、config、package.xml、CMakeLists、源码和历史 diff。
2. 再查外部已明确存在的项目：只在任务涉及训练时查看 `/home/xia/桌面/colt_trainer_py`。
3. 如果仍不确定，但可以做安全保守默认，则采用不触发运动、不改旧包、不提交大文件、不改变接口语义的方案，并在总结中写明假设。
4. 如果不确定项会影响硬件安全、公开接口、数据格式、模型发布或 Git 历史，必须先问用户。
5. 不得为了继续推进而编造不存在的文件、命令、节点、话题或测试结果。

默认保守假设：

- 当前阶段只做感知、坐标、RViz 和离线验证。
- 第一版实时主输入使用 Kinect2 QHD。
- 默认输出坐标系为 `base_footprint`。
- 模型训练默认 `YOLO11l-seg`，`YOLO11x-seg` 只做对比，`YOLO11m/s-seg` 是推理压力过大时的降级候选。
- 源椅和目标椅由后续 UI 人工指定，模型不区分 source/target 类别。
- 任何真实底盘、机械臂和抓取动作都不属于默认开发测试。
