# 整机验收记录

目录页把机器人标为“已验证 / 已支持”需要可核查的证据。这里记录本仓库（清单 + 本体配置）在真机上的验收结果；
后续每次改动清单、URDF 或升级原语/技能，在“新增记录”里追加，不要覆盖历史。

## 2026-11-05 — 整机 boot（8 个包全部拉起）

- 平台：Jetson Orin NX / aarch64 / Ubuntu 22.04 / ROS 2 Humble / `rmw_zenoh_cpp`
- 拉起：atlas(50051)、soma(50091，`soma.yaml`)、executor(50061)、pilot(50071)、liaison(50081)，
  以及 4 个原语（`robot_description`、`arm7aix_controller`、`o6_hand`、`orbbec_camera`）、
  2 个服务（`arm7aix_control`、`linker_hand_control`）、2 个技能（`hand_gesture`、`qmzs_grasp`）
- 证据：部署日志 `logs/rbnx.log`（2026-11-05 多轮 boot/shutdown，含两个服务的正常启停记录）
- 结论：**通过**

## 2026-11-05 — 真机抓取（`qmzs_grasp` pick）

- 感知：固定 Orbbec Gemini 336L，桌面单应 `calibration.json`；固定法兰 Z = 110 mm，
  姿态取自 `grasp_orientation.json`
- 流程：`pick`（VLM 定位绿色方块）→ 手张开 → 悬停 `target z + approach_height_m` → 下降 →
  O6 fist 闭合 → 稳定 → 抬起。**绿色方块被抓取并抬离桌面**
- 证据：23 s / 1280×720 运行录像（维护者留存）
- 结论：**PASS（抓取段）**；`grab` 复用的同段流程同样成立
- `home` 复位：已验证。未在清单里配置 `home_joints`（保持 `[]`），Robonix 自动解析为**零点位姿（初始状态）**
  作为 home 目标，复位到初始位姿正常。
- 未覆盖：`place`、`release`，以及多物体/失败重试路径。O6 接口在此技能里是开环的
  （`hand_open_settle_s` / `hand_close_settle_s`，不读 `get_state`），正常使用时应目视确认手指与物体

## 2026-11-05 — 构建与单元测试

- `./build.sh` 全部包构建通过；9 项单元测试通过；45 个文件语法检查通过
- 结论：**通过**（未做真机运动，与上面的抓取记录相互独立）

## 2026-11-06 — 现场调试会话

- 现场联调：整机 boot / shutdown 多轮正常，服务与技能无阻塞性错误
- 已知非阻塞告警：`Package database sync failed: Failed to write database: ~/.robonix/packages/db.json`
  （目录同步写入失败，不影响本地启动）；`arm7aix_control` 的 `on_shutdown` 返回 `None` 导致
  关闭时多一条 warn（不影响运行，后续在服务里修）

## 新增记录模板

```markdown
## YYYY-MM-DD — <一句话说明>

- 提交：`robot-qmzs-arm7aix@<commit>`
- 原语/技能版本：arm7aix_controller@<branch/commit>、o6_hand@…、orbbec_camera@…、
  qmzs_grasp@v0.1.3、hand_gesture@…
- 平台：… 标定：calibration.json 日期、pixel_to_pose 残差 ≤ __ mm
- 启动：`./build.sh` / `rbnx boot` 结果
- 功能：get_state / snapshot / detect_object / pixel_to_pose / pick / place / release / home /
  hand fist / open / gesture_dance —— 逐项注明通过或未覆盖
- 证据：日志片段、截图、录像位置
- 结论：通过 / 部分通过（说明未通过项）
```
