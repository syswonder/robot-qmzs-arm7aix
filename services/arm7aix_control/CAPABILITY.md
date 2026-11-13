# ARM7AIX 机械臂 MCP 控制服务

`arm7aix_control` 把 ARM7AIX 七轴机械臂的 ROS 2 话题接口包装成 Pilot /
`rbnx chat` 可直接调用的 MCP 工具。它不直接访问硬件：所有动作都发布到
`arm7aix_controller` 原语的话题，由原语完成规划、限位检查和电机协议。

## 工具

| 工具 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `move_joint` | `positions: float64[7]`（rad） | `accepted`, `reached`, `timed_out`, `elapsed_sec`, `final_positions[7]`, `detail` | 七轴位置目标（POS_VEL）。发布后等待到位或超时（`motion_timeout_sec`） |
| `move_pose` | `x,y,z`（m）+ `qx,qy,qz,qw` | 同上 | `base_link` 下的末端位姿目标（MoveP），同样等待到位/超时 |
| `enable_joints` | 无 | `accepted`, `detail` | 以当前测量位置使能七轴，不产生运动目标 |
| `disable_joints` | 无 | `accepted`, `detail` | 停止运动并失能七轴；**去掉保持力，机械臂可能下落** |
| `get_state` | 无 | 位置/速度/力矩（各 7）、末端位姿、`valid`、`feedback_age_sec`、`detail` | 读取缓存的关节与末端反馈；用于确认运动进度 |

## 行为与限制

- `move_joint` / `move_pose` 发布目标后会在 `motion_timeout_sec` 内等待反馈进入容差：
  `reached=true` 表示到位；`timed_out=true` 表示超时未到位（目标可能被原语拒绝，
  见原语日志）。`final_positions` 是最后一次实测角度/位姿。`motion_timeout_sec: 0`
  可退回“发布后立即返回”。
- 目标由 arm7aix_controller 校验并规划：超限、不可达或无法满足速度/加速度/
  跃度限制的目标会被拒绝并写入 `rbnx-boot/logs/arm7aix_controller.log`。
  `move_pose` 只约束 TCP 终点；中间 TCP 路径由关节空间轨迹决定。
- 收到首个有效运动命令时原语会自动使能七轴；也可先显式调用 `enable_joints`。
- `disable_joints` 不是硬件急停；它会移除电机保持力，调用前确认机械支撑。
- `dry_run: true` 时工具只记录、不发布消息，便于无硬件联调。
- 反馈超过 `feedback_stale_sec` 未更新时 `get_state.valid=false`。
