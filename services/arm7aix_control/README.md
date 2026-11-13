# arm7aix_control

ARM7AIX 七轴机械臂的 Robonix MCP 控制服务。把 `arm7aix_controller` 原语的
ROS 2 话题接口包装成 Pilot / `rbnx chat` 可调用的工具：

```
rbnx chat  ── MCP ──> arm7aix_control ── ROS 2 话题 ──> arm7aix_controller ── U2CAN ──> 机械臂
```

## 工具

`move_joint` / `move_pose` / `enable_joints` / `disable_joints` / `get_state`，
契约定义在 `capabilities/`，实现见 `arm7aix_control/main.py`。
`move_joint` / `move_pose` 会等反馈到位（或 `motion_timeout_sec` 超时）再返回
`reached` / `timed_out` / `final_positions`。详见 [CAPABILITY.md](CAPABILITY.md)。

## 构建 / 启动

由部署入口统一驱动（会把本包列在 `robonix_manifest.yaml` 的 `service:` 下）：

```bash
cd /path/to/arm7aix_robonix
./build.sh    # codegen 本包 MCP 契约
./start.sh    # boot 整栈（含本服务）
```

单独调试：

```bash
rbnx start -p services/arm7aix_control --endpoint 127.0.0.1:50051
```

## 安全

- 工具只做消息发布与反馈缓存，限位/规划/故障保护都在原语里；不要绕过原语直接驱动电机。
- `move_joint` / `move_pose` 会立即开始运动；调用前确认工作空间无人、无障碍。
- `disable_joints` 会去掉保持力，机械臂可能下落；它不是硬件急停。
- 现场先设 `dry_run: true` 联调工具链路，确认后再改成 `false`。
