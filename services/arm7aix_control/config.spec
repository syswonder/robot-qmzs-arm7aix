# arm7aix_control 部署配置说明（config.spec）

`robonix_manifest.yaml` 中该实例的 `config:` 原样传给 `on_init(cfg)`。
全部字段可选；默认值与本部署的 arm7aix_controller 配置对齐。

```yaml
service:
  - name: arm7aix_control
    path: ./services/arm7aix_control
    config:
      dry_run: false
      joint_names: [joint1, joint2, joint3, joint4, joint5, joint6, joint7]
      feedback_stale_sec: 1.0
      motion_timeout_sec: 30.0
      joint_tolerance_rad: 0.02
      pose_position_tolerance_m: 0.005
      pose_angle_tolerance_rad: 0.03
      topics:
        joint_states: /arm7aix/joint_states
        end_pose: /arm7aix/end_pose
        joint_command: /arm7aix/joint_command
        pos_command: /arm7aix/pos_command
        joint_enable: /arm7aix/joint_enable
        joint_disable: /arm7aix/joint_disable
```

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `dry_run` | bool | `false` | true 时 MCP 工具只记录、不发布 ROS 2 消息（无硬件联调用） |
| `joint_names` | 7 个 string | `joint1..joint7` | 关节顺序；必须与 `config/arm7aix.yaml` 的 `kinematics.joint_names` 一致 |
| `feedback_stale_sec` | float (s) | `1.0` | 超过该时长未收到反馈时 `get_state.valid=false`，运动工具也不再等待 |
| `motion_timeout_sec` | float (s) | `30.0` | `move_joint` / `move_pose` 等待到位的最长时间；`0` = 发布后立即返回不等待 |
| `joint_tolerance_rad` | float (rad) | `0.02` | 七轴位置与目标的误差小于该值即判定到位 |
| `pose_position_tolerance_m` | float (m) | `0.005` | 末端位置与目标的误差小于该值即判定到位 |
| `pose_angle_tolerance_rad` | float (rad) | `0.03` | 末端姿态四元数夹角小于该值即判定到位 |
| `topics.*` | string | 见上 | 必须是绝对 ROS 2 话题名；与 arm7aix_controller 的 `config.*_topic` 保持一致 |

关节限位、速度/加速度/跃度限制、轨迹规划、电机协议和故障诊断不在本服务里，
由 arm7aix_controller 原语按 `config/arm7aix.yaml` 执行。`motion_timeout_sec`
只是「等反馈到位」的上限，不是原语的运动超时；原语拒绝的目标会写入
`rbnx-boot/logs/arm7aix_controller.log`，最终位置会出现在工具返回的
`final_positions` 里。
