# Colt 实测操作说明

这套项目当前只做 3 件事：

- 看相机画面，识别椅子
- 在终端里选源椅和目标椅
- 控制二轴云台朝向源椅或目标椅

如果你没看过代码，只需要按下面步骤操作。

## 根目录的 3 个脚本

- `scripts/package_project.sh`
  - 在开发机上打包项目
  - 打包文件会放到项目目录外
- `scripts/install_runtime.sh`
  - 在实测机上安装 Python 运行环境
  - 强制使用 Python 3.11，并默认使用清华源
- `scripts/run_project.sh`
  - 在实测机上启动项目

## 一、在开发机上打包

进入工作空间后执行：

```bash
cd /home/xia/桌面/catkin_ws
./scripts/package_project.sh
```

执行后会生成一个压缩包，位置在 `catkin_ws` 目录外。

## 二、把压缩包拷到实测机并解压

把上一步生成的压缩包拷到实测机，然后解压到你想放的位置。

例子：

```bash
mkdir -p ~/colt_runtime
tar -xzf catkin_ws_runtime_*.tar.gz -C ~/colt_runtime
cd ~/colt_runtime/catkin_ws
```

## 三、在实测机上安装环境

进入工作空间后执行：

```bash
cd ~/colt_runtime/catkin_ws
./scripts/install_runtime.sh
```

这个脚本会自动做这几件事：

- 用清华镜像把 `Python 3.11` 安装到当前工作空间的 `.python311/`
- 在当前工作空间里创建 `.venv-py311`
- 安装项目运行需要的 Python 依赖

## 四、确认现场基础设备已经启动

运行本项目之前，现场需要先有这 3 样东西：

- Kinect2 相机已经正常出图
- 云台驱动已经正常启动
- 机器人当前世界坐标已经正常发布

这个项目不会代替你启动这些硬件。

## 五、启动项目

进入工作空间后执行：

```bash
cd ~/colt_runtime/catkin_ws
./scripts/run_project.sh
```

这个脚本会自动做 4 件事：

- 必要时编译工作空间
- 检查检测模型运行包是否完整
- 启动检测、云台控制和终端选择界面
- 启动 RViz 标记发布脚本

## 六、怎么操作

启动后，终端里会出现当前看到的椅子列表。

常用命令只有 4 个：

- `s 1`
  - 把第 1 把椅子设为源椅
- `t 2`
  - 把第 2 把椅子设为目标椅
- `swap`
  - 在已经选好源椅和目标椅后，让云台从朝向源椅切到朝向目标椅
- `clear all`
  - 清空当前选择

如果你同时开着 RViz，可以直接订阅这个话题看标记：

- `/colt/ui/rviz_markers`

## 七、当前运行规则

- 源椅和目标椅没有同时指定完之前，云台会在小范围内来回扫视
- 源椅和目标椅都指定完后，云台默认先朝向源椅
- 输入 `swap` 后，云台改为朝向目标椅
- 云台运动是受限的，不会大角度乱转

## 八、如果启动失败

先检查这几项：

- `src/colt/colt_bridle/models/runtime/current` 是否存在
- 相机、云台、机器人坐标是否已经按现场原方式启动
- `.venv-py311` 是否已经装好

如果只是想看更详细的包内说明，再看这些文件：

- `src/colt/README.md`
- `src/colt/colt_bridle/README.md`
- `src/colt/colt_ui/README.md`
