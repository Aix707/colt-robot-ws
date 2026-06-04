# Colt 实测操作说明

这套项目当前只做 4 件事：

- 看相机画面并识别椅子、椅面和源椅铝块
- 在 OpenCV 窗口里点选源椅和目标椅
- 控制二轴云台朝向源椅或目标椅
- 将小车和对象状态上传到后台

运行时不创建虚拟环境，ROS/Python 节点统一使用系统 `python3`。

## 根目录脚本

- `scripts/package_project.sh`：在开发机打包项目。
- `scripts/install_runtime.sh`：检查系统 Python 依赖和 ONNX runtime，不安装、不创建 venv。
- `scripts/run_project.sh`：在实测机按旧的一键方式启动外部设备、检测、云台控制和 OpenCV 选择窗口。
- `scripts/record_bag.sh`：记录最小 RGB/depth/camera_info/TF/joint_states bag。

## 依赖安装

依赖需要手动安装，建议命令：

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-opencv libgl1 libglib2.0-0

sudo -H python3 -m pip install -U "pip<25" setuptools wheel

sudo -H python3 -m pip install \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  "numpy==1.24.4" \
  "torch==2.4.1+cpu" \
  "torchvision==0.19.1+cpu" \
  "opencv-python==4.10.0.84" \
  "onnx==1.17.0" \
  "onnxruntime==1.17.3" \
  "ultralytics==8.4.56" \
  pyyaml rospkg catkin_pkg
```

检查当前机器：

```bash
cd /home/xia/桌面/catkin_ws
./scripts/install_runtime.sh
```

## 推荐分层启动

当前运行链路拆成两层：

- 外部依赖节点：Kinect2、`wpv4_core`、`wpv4_pt`、机器人 TF、`map -> odom` 静态 TF。
- 自建功能节点：检测、云台跟踪、OpenCV 选择窗口、Paddock 遥测上传。

终端 1，启动外部依赖：

```bash
cd /home/xia/桌面/catkin_ws
source devel/setup.bash
roslaunch colt_bridle external_nodes.launch
```

如果与其他项目合并运行，且其他项目已经启动了某些外部节点，就关闭重复项，例如：

```bash
roslaunch colt_bridle external_nodes.launch \
  start_base:=false \
  start_camera:=false \
  start_pt_driver:=false \
  start_map_odom_tf:=false
```

终端 2，启动检测和云台跟踪：

```bash
source devel/setup.bash
roslaunch colt_bridle online_perception.launch start_pt_control:=true
```

终端 3，启动 OpenCV 选择窗口：

```bash
source devel/setup.bash
roslaunch colt_ui cv_selector.launch
```

终端 4，启动 Paddock 上传：

```bash
source devel/setup.bash
roslaunch paddock telemetry_upload.launch
```

如果合并项目只提供 `base_footprint` 而没有 `body_link`，启动自建功能时改传：

```bash
robot_frame:=base_footprint
```

## 一键启动

```bash
cd /home/xia/桌面/catkin_ws
./scripts/run_project.sh
```

脚本会：

- 必要时运行 `catkin_make`
- 通过 `field_runtime.launch` 启动外部依赖节点；该入口当前只 include `external_nodes.launch`
- 等待相机、`/joint_states` 和 `map -> body_link` TF
- 检查 `models/runtime/current` 和 3 个 ONNX
- 启动检测与云台控制
- 有 `DISPLAY` 时启动 OpenCV 椅子选择窗口

一键脚本适合单独运行本项目。与其他项目合并运行时，优先使用上面的分层启动方式，避免重复启动底盘、相机、云台或 TF。

## OpenCV 窗口操作

- 鼠标左键点击椅子：设为当前候选
- `s`：把候选椅子设为 source
- `t`：把候选椅子设为 target
- `w`：在 source/target 朝向状态之间切换
- `c`：清空 source、target 和 `pt_state`
- `q`：退出窗口

UI 继续发布：

```text
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
/colt/ui/pt_state
```

窗口下方会显示源椅、源椅面、铝块、目标椅和目标椅面的实时 `x/y/z` 坐标。

## 当前运行规则

- 源椅和目标椅没有同时指定完之前，云台在 `wp_tilt` 左右小范围扫视。
- `wp_pitch` 默认固定向前，不跟随 y 误差；需要时可通过参数打开小幅 pitch 修正。
- 源椅和目标椅都指定完后，默认先朝向源椅。
- `w` 切换后，云台改为朝向目标椅。

## 离线 bag 测试

`/home/xia/桌面/colt_capture.bag` 只包含 RGB/depth/camera_info，适合验证检测和 OpenCV UI，不验证 TF 和云台。

```bash
source devel/setup.bash
roslaunch colt_bridle online_perception.launch \
  target_frame:=kinect2_rgb_optical_frame \
  robot_frame:=kinect2_rgb_optical_frame
```

终端 2：

```bash
source devel/setup.bash
roslaunch colt_ui cv_selector.launch
```

终端 3：

```bash
source devel/setup.bash
rosbag play /home/xia/桌面/colt_capture.bag --clock
```

## 启动失败时先看

- `src/colt/colt_bridle/models/runtime/current` 是否指向 `cpu_v001`
- `./scripts/install_runtime.sh` 是否输出 `"ready": true`
- Kinect2、`/dev/wpv4_pt`、`/dev/wpv4_base` 是否已连接
- 脚本最后卡在哪个 `Waiting for ...` 话题或 TF
