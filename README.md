# robot-qmzs-arm7aix

qmzs/ARM7AIX 整机部署仓库（Robonix 机器人部署）：**固定基座七轴机械臂 + LinkerHand O6 灵巧手 + Orbbec Gemini 336L RGB-D 相机**。
按 Robonix 规范，本仓库只做**组装**：原语、服务、技能各自独立成包，这里只保存本体专属的清单、URDF、配置与启动脚本。

- 目录条目：`robonix.robot.qmzs.arm7aix`（https://packages.robonix.ai/robots/）
- 清单入口：`robonix_manifest.yaml`（`rbnx boot` 的入口）
- 本体描述：`soma.yaml`

## 硬件与平台

| 项 | 型号 / 规格 |
| --- | --- |
| 机械臂 | ARM7AIX 七轴，Damiao 电机，U2CAN 串口适配器（`/dev/ttyACM0`） |
| 末端执行器 | LinkerHand O6 左手（六轴五指），XCAN-USB → SocketCAN `can2`，1 Mbps |
| 相机 | Orbbec Gemini 336L（固定安装，640×480@15 MJPG，与手眼标定分辨率一致） |
| 计算平台 | Jetson Orin NX（aarch64），Ubuntu 22.04 |
| 软件 | ROS 2 Humble、`rmw_zenoh_cpp`、Robonix CLI（`rbnx`） |

## 支持矩阵

| 项目 | 状态 | 验证日期 | 说明 |
| --- | --- | --- | --- |
| 构建（`./build.sh`） | 已验证 | 2026-11-05 | 全部包构建通过 |
| 单元测试 | 已验证 | 2026-11-05 | 9 项通过 |
| 整机 boot（8 个包全部拉起） | 已验证 | 2026-11-05 | atlas/soma/executor/pilot/liaison + 4 原语 + 2 服务 + 2 技能，日志见 `logs/rbnx.log` |
| `rbnx chat` 工具调用 | 已验证 | 2026-11-05 | `get_state` / `snapshot` / `detect_object` / `pick` 实机可用 |
| 真机抓取（`qmzs_grasp` pick） | 已验证 | 2026-11-05 | 固定相机 + 桌面标定面抓绿色方块成功（23 s 录像留存） |
| `home` 复位 | 已验证 | 2026-11-05 | 未配置 `home_joints` 时 Robonix 自动解析为零点位姿（初始状态） |
| place / release | 未验证 | — | O6 手部为开环控制，现场低速试跑 |

详细证据见 [`docs/validation.md`](docs/validation.md)。

## 仓库结构

```
robonix_manifest.yaml   # 整机清单：catalog 元数据 / system / primitive / service / skill
soma.yaml               # 本体描述：arm + hand + camera 三个部件与对外能力
urdf/                   # 唯一完整 URDF 与网格（arm7aix.urdf + meshes/）
config/                 # 本体专属配置（目前只有手眼标定产物目录，运行时生成、不入库）
services/               # 两个 MCP 服务：arm7aix_control / linker_hand_control（随本仓库发布）
assets/                 # 目录页展示图（可选；promo/01.jpg 1600×1000）
docs/                   # 标定说明、验收记录
build.sh start.sh setup.sh ros2_env.sh   # 便捷入口
.env.example            # VLM 凭据模板（.env 不入库）
LICENSE                 # MulanPSL-2.0
```

## 包与依赖

| 组件 | 来源 | 角色 |
| --- | --- | --- |
| `robot_description` | https://github.com/syswonder/primitive-robot-description-rbnx | 机器人描述原语 |
| `arm7aix_controller` | https://github.com/syswonder/primitive-qmzs-arm7aix-rbnx | 七轴臂原语（ROS 2 话题：joint_states/end_pose/joint_command/pos_command/enable/disable） |
| `o6_hand` | https://github.com/syswonder/primitive-linkerbot-linker_hand_o6-hand-rbnx | O6 灵巧手原语（CAN 直连，hand/* gRPC 契约） |
| `orbbec_camera` | https://github.com/syswonder/primitive-orbbec-camera-rbnx | Gemini 336L RGB-D 原语（camera/*） |
| `arm7aix_control` | 本仓库 `services/arm7aix_control` | MCP 服务：move_joint / move_pose / enable_joints / disable_joints / get_state |
| `linker_hand_control` | 本仓库 `services/linker_hand_control` | MCP 服务：手部 fist / open 预设 |
| `hand_gesture` | https://github.com/syswonder/skill-hand-gesture-rbnx | 技能：手势动画 |
| `qmzs_grasp` | https://github.com/syswonder/skill-qmzs-grasp-rbnx（`v0.1.3`） | 技能：抓取/放置/复位、像素→基座定位、VLM 目标检测 |

两个服务随本仓库发布（清单里用 `path:` 引用）；原语与技能用 `url:` + `branch` 引用，换版本只改清单。

## 环境要求

- Ubuntu 22.04 / aarch64（x86 亦可，需自备 CAN 与串口适配器）
- ROS 2 Humble（含 `rmw_zenoh_cpp`）
- Robonix CLI：完成 `rbnx setup /path/to/robonix`，并把 `rbnx` 放进 PATH
- Python 3.10+（用系统 Python 建 venv，`--system-site-packages` 复用 rclpy）

## 安装

```bash
git clone https://github.com/syswonder/robot-qmzs-arm7aix
cd robot-qmzs-arm7aix
./setup.sh                 # 建 .venv、装 requirements、检查 ROS 2 与 Robonix
cp .env.example .env       # 填 VLM_BASE_URL / VLM_API_KEY / VLM_MODEL（可留空）
sudo usermod -aG dialout "$USER"   # 串口权限（重新登录生效）
```

拉起 CAN（每次上电后执行，接口名与清单 `can_iface` 保持一致）：

```bash
sudo ip link set can2 type can bitrate 1000000
sudo ip link set can2 up
ip -details link show can2
```

## 构建

```bash
./build.sh
```

首次会 clone 原语/技能到 `rbnx-boot/cache/`，并 colcon 编译 vendored OrbbecSDK_ROS2，耗时较长（一次即可）。
构建失败常见原因：`rbnx` 不在 PATH、ROS 2 未 source、网络无法访问 GitHub。

## 手眼标定（必做，产物不入库）

抓取技能需要 `config/handeye/calibration.json`（桌面单应：去畸变像素 → base_link XY）与
`config/handeye/grasp_orientation.json`（目标法兰 Z + 四元数）。这两份文件**每台机器现场生成**，
不随仓库发布（`config/handeye/*.json`、`*.npy` 已被 `.gitignore` 忽略）。

1. 用 handeye-calibration 完成相机内参与桌面标定，**分辨率必须是 640×480@15 MJPG**（与清单里的相机配置一致）；
2. 导出 `calibration.json`、`image_to_robot_xy.npy`、`grasp_orientation.json`，拷入 `config/handeye/`；
3. 未标定时：`detect_object` / `snapshot` / `calibration_status` 可用，`pixel_to_pose`、`pick` 会报错。

详见 [`docs/calibration.md`](docs/calibration.md)。

## 启动

```bash
./start.sh
```

脚本会加载 `.env`、source ROS 2、预检串口与 CAN、必要时拉起 `rmw_zenohd`，然后 `rbnx boot`。
三项设备都只能有一个进程持有（U2CAN 串口、CAN 接口、Orbbec 相机）：先停掉手眼标定网页、厂商 GUI、
其他相机驱动，再 boot。确认安全时可 `SKIP_DEVICE_PREFLIGHT=1 ./start.sh` 跳过占用检查。

## 验收

```bash
rbnx chat            # 另开终端（与 boot 同一环境）
```

建议顺序：

1. `get_state` 读关节状态（确认七轴有反馈，不运动）；
2. `snapshot` + `detect_object` 确认相机画面与检测框（`qmzs_grasp` 默认 `dry_run: true`，只算不发）；
3. 核对 `pixel_to_pose` 的 XY 与标注图，再把清单里 `qmzs_grasp.config.dry_run` 改成 `false` 重 boot；
4. 真机抓放：`pick` / `place` / `release` / `home`，从空载、低速开始。

记录验收证据（日志、截图、提交号）到 [`docs/validation.md`](docs/validation.md)。

## 已知限制

- 固定基座，无移动底盘；抓取 Z 依赖标定高度，只适用于标定平面附近。
- 灵巧手是六轴结构，Soma 不提供开合聚合快照（读 `hand/get_state`）。
- 不通过 Robonix 暴露 MIT 力矩模式。
- `qmzs_grasp` 的 `grab` 需要 `grasp_pose`（默认留空，按现场补）；`home` 不需要配置：未填 `home_joints`
  时 Robonix 自动解析为零点位姿（初始状态）。

## 许可与维护

- 许可：MulanPSL-2.0（见 `LICENSE`）。
- 维护者：`Joker.Yun <2353493891@qq.com>`。
- 原语/技能的代码问题请提到各自仓库；本机的本体参数、清单与启动脚本问题提到本仓库。
