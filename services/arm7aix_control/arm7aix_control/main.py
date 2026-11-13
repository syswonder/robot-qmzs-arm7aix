#!/usr/bin/env python3
# SPDX-License-Identifier: MulanPSL-2.0
"""arm7aix_control — ARM7AIX 机械臂控制服务（Pilot / `rbnx chat` 的 MCP 工具层）。

把 arm7aix_controller 原语的 ROS 2 话题接口包装成 5 个 MCP 工具：

  move_joint      七轴位置目标（rad）        -> /arm7aix/joint_command
  move_pose       末端笛卡尔位姿目标          -> /arm7aix/pos_command
  enable_joints   使能七轴（保持当前位置）    -> /arm7aix/joint_enable
  disable_joints  停止并失能七轴（会掉力）    -> /arm7aix/joint_disable
  get_state       读取缓存的关节/末端反馈     <- /arm7aix/joint_states, /arm7aix/end_pose

职责边界：本包只做「工具参数校验 -> ROS 2 消息发布」和反馈缓存；关节限位、
轨迹规划、电机协议、故障诊断全部由 arm7aix_controller 原语负责。原语日志在
`rbnx-boot/logs/arm7aix_controller.log`。

注意：joint_command / pos_command 是输入流，没有逐条完成应答；工具返回
accepted=true 只表示消息已发布，运动是否完成要用 get_state 轮询判断。
"""
from __future__ import annotations

import logging
import math
import threading
import time

from robonix_api import Service, Ok, Err

# codegen 产物（capabilities/lib/arm7aix_control/srv/*.srv）
from arm7aix_control_mcp import (
    MoveJoint_Request, MoveJoint_Response,
    MovePose_Request, MovePose_Response,
    EnableJoints_Request, EnableJoints_Response,
    DisableJoints_Request, DisableJoints_Response,
    GetState_Request, GetState_Response,
)

service = Service(id="arm7aix_control", namespace="robonix/service/arm7aix_control")

log = logging.getLogger("arm7aix_control")
logging.basicConfig(level=logging.INFO, format="[arm7aix_control] %(levelname)s %(message)s")

JOINT_COUNT = 7

DEFAULT_TOPICS = {
    "joint_states": "/arm7aix/joint_states",
    "end_pose": "/arm7aix/end_pose",
    "joint_command": "/arm7aix/joint_command",
    "pos_command": "/arm7aix/pos_command",
    "joint_enable": "/arm7aix/joint_enable",
    "joint_disable": "/arm7aix/joint_disable",
}

_state: dict = {
    # config（on_init 填充）
    "dry_run": False,
    "joint_names": tuple(f"joint{i}" for i in range(1, JOINT_COUNT + 1)),
    "topics": dict(DEFAULT_TOPICS),
    "feedback_stale_sec": 1.0,
    # 运动完成判定：move_* 工具发布后等待反馈到位（0 = 立即返回，不等待）
    "motion_timeout_sec": 30.0,
    "joint_tolerance_rad": 0.02,
    "pose_position_tolerance_m": 0.005,
    "pose_angle_tolerance_rad": 0.03,
    # ROS 2（懒初始化，见 _ensure_ros）
    "ros_ready": False,
    "ros_lock": threading.Lock(),
    "rclpy": None,
    "node": None,
    "executor": None,
    "spin_thread": None,
    "pubs": {},
    "msgs": {},
    # 反馈缓存
    "cache_lock": threading.Lock(),
    "joint_state": None,
    "joint_state_t": 0.0,
    "end_pose": None,
    "end_pose_t": 0.0,
    # 反馈到达统计（用于对比 chat / 直接下发的时序）
    "fb_stats": {"last_t": None, "max_gap_s": 0.0, "samples": 0},
}


# ── ROS 2 plumbing ───────────────────────────────────────────────────

def _on_joint_state(msg) -> None:
    now = time.monotonic()
    with _state["cache_lock"]:
        stats = _state["fb_stats"]
        previous = stats["last_t"]
        if previous is not None:
            gap = now - previous
            if gap > stats["max_gap_s"]:
                stats["max_gap_s"] = gap
        stats["last_t"] = now
        stats["samples"] += 1
        _state["joint_state"] = msg
        _state["joint_state_t"] = now


def _on_end_pose(msg) -> None:
    with _state["cache_lock"]:
        _state["end_pose"] = msg
        _state["end_pose_t"] = time.monotonic()


def _reset_fb_stats() -> None:
    with _state["cache_lock"]:
        _state["fb_stats"] = {"last_t": None, "max_gap_s": 0.0, "samples": 0}


def _fb_stats() -> tuple[int, float]:
    with _state["cache_lock"]:
        stats = _state["fb_stats"]
        return int(stats["samples"]), float(stats["max_gap_s"])


def _ensure_ros() -> None:
    """懒初始化 rclpy 节点、发布/订阅。可重复调用。"""
    if _state["ros_ready"]:
        return
    with _state["ros_lock"]:
        if _state["ros_ready"]:
            return
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import (
                DurabilityPolicy,
                HistoryPolicy,
                QoSProfile,
                ReliabilityPolicy,
            )
            from geometry_msgs.msg import Pose
            from sensor_msgs.msg import JointState
            from std_msgs.msg import Empty
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"ROS 2 Python 依赖不可用（先 source ROS 2 Humble 环境）：{exc}"
            ) from exc

        rclpy.init(args=None)
        node = rclpy.create_node("arm7aix_control")

        # 命令侧：原语用 qos=1（reliable, depth 1）订阅，这里保持一致。
        cmd_qos = QoSProfile(
            depth=1,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        # 反馈侧：原语以 best_effort 发布，订阅端必须用 best_effort 才能匹配。
        fb_qos = QoSProfile(
            depth=5,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        topics = _state["topics"]
        _state["pubs"] = {
            "joint_command": node.create_publisher(JointState, topics["joint_command"], cmd_qos),
            "pos_command": node.create_publisher(Pose, topics["pos_command"], cmd_qos),
            "joint_enable": node.create_publisher(Empty, topics["joint_enable"], cmd_qos),
            "joint_disable": node.create_publisher(Empty, topics["joint_disable"], cmd_qos),
        }
        node.create_subscription(JointState, topics["joint_states"], _on_joint_state, fb_qos)
        node.create_subscription(Pose, topics["end_pose"], _on_end_pose, fb_qos)

        executor = SingleThreadedExecutor()
        executor.add_node(node)
        spin_thread = threading.Thread(
            target=executor.spin, name="arm7aix-control-ros", daemon=True
        )
        spin_thread.start()

        _state.update(
            rclpy=rclpy,
            node=node,
            executor=executor,
            spin_thread=spin_thread,
            msgs={"JointState": JointState, "Pose": Pose, "Empty": Empty},
            ros_ready=True,
        )
        log.info(
            "ROS 2 ready: pubs=%s subs=[%s, %s]",
            list(_state["pubs"]),
            topics["joint_states"],
            topics["end_pose"],
        )


def _publish(key: str, msg) -> bool:
    """发布一条消息；dry_run 时只记录不发布。返回是否真正发布。"""
    if not _state["ros_ready"]:
        _ensure_ros()
    if _state["dry_run"]:
        log.info("dry_run: 跳过发布 %s -> %s", key, _state["topics"][key])
        return False
    _state["pubs"][key].publish(msg)
    return True


def _stamp(node):
    return node.get_clock().now().to_msg()


def _finite(values) -> bool:
    return all(math.isfinite(float(v)) for v in values)


def _cached_joint_state():
    """返回 (JointState|None, age_sec)。"""
    with _state["cache_lock"]:
        js = _state["joint_state"]
        t = _state["joint_state_t"]
    if js is None:
        return None, float("inf")
    return js, max(0.0, time.monotonic() - t)


def _cached_end_pose():
    with _state["cache_lock"]:
        pose = _state["end_pose"]
        t = _state["end_pose_t"]
    if pose is None:
        return None, float("inf")
    return pose, max(0.0, time.monotonic() - t)


def _positions_from(joint_state) -> list[float]:
    if joint_state is None:
        return [0.0] * JOINT_COUNT
    values = [float(v) for v in joint_state.position][:JOINT_COUNT]
    values.extend([0.0] * (JOINT_COUNT - len(values)))
    return values


async def _wait_joint_target(target: list[float], timeout: float):
    """等待七轴反馈接近 target。返回 (reached, timed_out, elapsed, final_positions)。"""
    import asyncio

    stale = _state["feedback_stale_sec"]
    tol = _state["joint_tolerance_rad"]
    start = time.monotonic()
    final = [0.0] * JOINT_COUNT
    while True:
        joint_state, age = _cached_joint_state()
        if joint_state is not None:
            final = _positions_from(joint_state)
            if age <= stale and all(
                abs(a - b) <= tol for a, b in zip(final, target)
            ):
                return True, False, time.monotonic() - start, final
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return False, True, elapsed, final
        await asyncio.sleep(0.05)


async def _wait_pose_target(target: list[float], timeout: float):
    """等待末端位姿接近 target=[x,y,z,qx,qy,qz,qw]。返回 (reached, timed_out, elapsed, final_positions)。"""
    import asyncio

    stale = _state["feedback_stale_sec"]
    pos_tol = _state["pose_position_tolerance_m"]
    ang_tol = _state["pose_angle_tolerance_rad"]
    start = time.monotonic()
    while True:
        pose, age = _cached_end_pose()
        final = _positions_from(_cached_joint_state()[0])
        if pose is not None and age <= stale:
            dx = pose.position.x - target[0]
            dy = pose.position.y - target[1]
            dz = pose.position.z - target[2]
            pos_err = math.sqrt(dx * dx + dy * dy + dz * dz)
            qp = [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]
            qt = target[3:7]
            na = math.sqrt(sum(v * v for v in qp))
            nb = math.sqrt(sum(v * v for v in qt))
            if na > 1e-9 and nb > 1e-9:
                dot = abs(sum(a * b for a, b in zip(qp, qt))) / (na * nb)
                dot = min(1.0, max(-1.0, dot))
                ang_err = 2.0 * math.acos(dot)
                if pos_err <= pos_tol and ang_err <= ang_tol:
                    return True, False, time.monotonic() - start, final
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return False, True, elapsed, final
        await asyncio.sleep(0.05)


# ── MCP 工具 ─────────────────────────────────────────────────────────

@service.mcp("robonix/service/arm7aix_control/move_joint")
async def move_joint(req: MoveJoint_Request) -> MoveJoint_Response:
    """Move all seven ARM7AIX joints to target positions in radians (POS_VEL mode).

    The arm may start moving immediately — confirm the workspace is clear and the
    target is reachable/within limits before using this tool. This call blocks
    until every joint is within joint_tolerance_rad of the target (reached=true)
    or motion_timeout_sec elapses (timed_out=true); final_positions are the last
    measured angles, so check them against the target. The arm primitive plans
    the trajectory with its configured limits and logs rejected targets."""
    positions = [float(v) for v in req.positions]
    if len(positions) != JOINT_COUNT:
        return MoveJoint_Response(
            accepted=False,
            detail=f"positions 需要 {JOINT_COUNT} 个关节角，收到 {len(positions)} 个",
        )
    if not _finite(positions):
        return MoveJoint_Response(accepted=False, detail="positions 含 NaN/Inf")

    joint_state, age = _cached_joint_state()
    try:
        _ensure_ros()
        _reset_fb_stats()
        JointState = _state["msgs"]["JointState"]
        msg = JointState()
        msg.header.stamp = _stamp(_state["node"])
        msg.name = list(_state["joint_names"])
        msg.position = positions
        published = _publish("joint_command", msg)
        if published:
            log.info("move_joint publish: target=%s", [round(v, 6) for v in positions])
    except Exception as exc:  # noqa: BLE001
        log.exception("move_joint 发布失败")
        return MoveJoint_Response(accepted=False, detail=f"发布失败：{exc}")

    shown = ", ".join(f"{v:.4f}" for v in positions)
    before = _positions_from(joint_state)
    if not published:
        return MoveJoint_Response(
            accepted=True,
            final_positions=before,
            detail=f"DRY_RUN：未发布关节目标 [{shown}] rad",
        )

    timeout = _state["motion_timeout_sec"]
    if timeout <= 0:
        return MoveJoint_Response(
            accepted=True,
            final_positions=before,
            detail=f"已发布关节目标 [{shown}] rad（motion_timeout_sec=0，未等待到位）",
        )
    if joint_state is None or age > _state["feedback_stale_sec"]:
        return MoveJoint_Response(
            accepted=True,
            final_positions=before,
            detail=f"已发布关节目标 [{shown}] rad；但没有新鲜关节反馈，无法确认是否到位",
        )

    reached, timed_out, elapsed, final = await _wait_joint_target(positions, timeout)
    final = [round(v, 4) for v in final]
    if reached:
        detail = (
            f"已到位：{elapsed:.2f}s 内七轴均进入 ±{_state['joint_tolerance_rad']} rad 容差；"
            f"final={final}"
        )
    elif timed_out:
        detail = (
            f"超时未到位：{timeout:.1f}s 后仍未进入 ±{_state['joint_tolerance_rad']} rad；"
            f"final={final}。目标可能被原语拒绝（见 rbnx-boot/logs/arm7aix_controller.log）"
        )
    else:
        detail = f"已发布关节目标 [{shown}] rad；final={final}"
    samples, max_gap = _fb_stats()
    log.info(
        "move_joint: reached=%s timed_out=%s elapsed=%.2fs fb_samples=%d fb_max_gap=%.3fs final=%s",
        reached, timed_out, elapsed, samples, max_gap, final,
    )
    return MoveJoint_Response(
        accepted=True,
        reached=reached,
        timed_out=timed_out,
        elapsed_sec=round(elapsed, 3),
        final_positions=final,
        detail=detail,
    )


@service.mcp("robonix/service/arm7aix_control/move_pose")
async def move_pose(req: MovePose_Request) -> MovePose_Response:
    """Move the arm tool to a Cartesian pose target in the base_link frame.

    Position is metres (x, y, z); orientation is a quaternion in xyzw order
    (normalised by the primitive). The arm may start moving immediately. This
    call blocks until the tool pose is within pose_position_tolerance_m /
    pose_angle_tolerance_rad of the target (reached=true) or motion_timeout_sec
    elapses (timed_out=true). The primitive's planner rejects unreachable or
    limit-violating targets (see its log)."""
    values = [float(req.x), float(req.y), float(req.z),
              float(req.qx), float(req.qy), float(req.qz), float(req.qw)]
    if not _finite(values):
        return MovePose_Response(accepted=False, detail="pose 含 NaN/Inf")
    qnorm = math.sqrt(sum(v * v for v in values[3:7]))
    if qnorm < 1e-6:
        return MovePose_Response(accepted=False, detail="四元数模长为 0")
    target_q = [v / qnorm for v in values[3:7]]
    target = values[:3] + target_q

    joint_state, age = _cached_joint_state()
    try:
        _ensure_ros()
        _reset_fb_stats()
        Pose = _state["msgs"]["Pose"]
        msg = Pose()
        msg.position.x, msg.position.y, msg.position.z = values[0], values[1], values[2]
        msg.orientation.x, msg.orientation.y = target_q[0], target_q[1]
        msg.orientation.z, msg.orientation.w = target_q[2], target_q[3]
        published = _publish("pos_command", msg)
        if published:
            log.info("move_pose publish: target=%s", [round(v, 6) for v in target])
    except Exception as exc:  # noqa: BLE001
        log.exception("move_pose 发布失败")
        return MovePose_Response(accepted=False, detail=f"发布失败：{exc}")

    before = _positions_from(joint_state)
    shown = (
        f"pos=({values[0]:.4f}, {values[1]:.4f}, {values[2]:.4f}) m "
        f"quat=({target_q[0]:.4f}, {target_q[1]:.4f}, {target_q[2]:.4f}, {target_q[3]:.4f})"
    )
    if not published:
        return MovePose_Response(
            accepted=True,
            final_positions=before,
            detail=f"DRY_RUN：未发布笛卡尔目标 {shown}",
        )

    timeout = _state["motion_timeout_sec"]
    if timeout <= 0:
        return MovePose_Response(
            accepted=True,
            final_positions=before,
            detail=f"已发布笛卡尔目标 {shown}（motion_timeout_sec=0，未等待到位）",
        )
    pose, pose_age = _cached_end_pose()
    if pose is None or pose_age > _state["feedback_stale_sec"]:
        return MovePose_Response(
            accepted=True,
            final_positions=before,
            detail=f"已发布笛卡尔目标 {shown}；但没有新鲜末端位姿反馈，无法确认是否到位",
        )

    reached, timed_out, elapsed, final = await _wait_pose_target(target, timeout)
    final = [round(v, 4) for v in final]
    if reached:
        detail = (
            f"已到位：{elapsed:.2f}s 内末端位姿进入 "
            f"{_state['pose_position_tolerance_m']} m / {_state['pose_angle_tolerance_rad']} rad 容差；"
            f"final={final}"
        )
    elif timed_out:
        detail = (
            f"超时未到位：{timeout:.1f}s 后仍未进入容差；final={final}。"
            "目标可能被原语拒绝（见 rbnx-boot/logs/arm7aix_controller.log）"
        )
    else:
        detail = f"已发布笛卡尔目标 {shown}；final={final}"
    samples, max_gap = _fb_stats()
    log.info(
        "move_pose: reached=%s timed_out=%s elapsed=%.2fs fb_samples=%d fb_max_gap=%.3fs",
        reached, timed_out, elapsed, samples, max_gap,
    )
    return MovePose_Response(
        accepted=True,
        reached=reached,
        timed_out=timed_out,
        elapsed_sec=round(elapsed, 3),
        final_positions=final,
        detail=detail,
    )


@service.mcp("robonix/service/arm7aix_control/enable_joints")
def enable_joints(req: EnableJoints_Request) -> EnableJoints_Response:
    """Enable all seven ARM7AIX drives in POS_VEL at their measured positions.

    This does not create a motion target, so the arm should not move (small
    position corrections during mode switch are possible). Motion commands also
    auto-enable the arm, so this is only needed for an explicit preparation
    step. Refused if a motion is currently executing (the primitive logs why)."""
    try:
        _ensure_ros()
        Empty = _state["msgs"]["Empty"]
        published = _publish("joint_enable", Empty())
    except Exception as exc:  # noqa: BLE001
        log.exception("enable_joints 发布失败")
        return EnableJoints_Response(accepted=False, detail=f"发布失败：{exc}")
    prefix = "DRY_RUN：未发布" if not published else "已发布使能请求"
    return EnableJoints_Response(accepted=True, detail=prefix)


@service.mcp("robonix/service/arm7aix_control/disable_joints")
def disable_joints(req: DisableJoints_Request) -> DisableJoints_Response:
    """Stop motion and disable all seven ARM7AIX drives.

    WARNING: holding torque is removed and the arm may fall — make sure the arm
    is mechanically supported before calling. This is NOT a hardware emergency
    stop; keep the physical E-stop available. The primitive logs failures."""
    try:
        _ensure_ros()
        Empty = _state["msgs"]["Empty"]
        published = _publish("joint_disable", Empty())
    except Exception as exc:  # noqa: BLE001
        log.exception("disable_joints 发布失败")
        return DisableJoints_Response(accepted=False, detail=f"发布失败：{exc}")
    prefix = "DRY_RUN：未发布" if not published else "已发布失能请求（电机将失去保持力）"
    return DisableJoints_Response(accepted=True, detail=prefix)


@service.mcp("robonix/service/arm7aix_control/get_state")
def get_state(req: GetState_Request) -> GetState_Response:
    """Read the latest seven-axis joint feedback and tool pose from the arm primitive.

    Use this after move_joint / move_pose to check whether the arm reached the
    target, and before motion to see the current positions. valid=false means no
    fresh feedback arrived within feedback_stale_sec (the arm primitive may be
    unavailable or not publishing)."""
    with _state["cache_lock"]:
        joint_state = _state["joint_state"]
        joint_t = _state["joint_state_t"]
        end_pose = _state["end_pose"]
        pose_t = _state["end_pose_t"]

    if joint_state is None:
        return GetState_Response(
            valid=False,
            feedback_age_sec=float("inf"),
            detail="尚未收到关节反馈；确认 arm7aix_controller 已激活并发布 /arm7aix/joint_states",
        )

    age = max(0.0, time.monotonic() - joint_t)
    stale = _state["feedback_stale_sec"]
    valid = age <= stale

    positions = [float(v) for v in joint_state.position][:JOINT_COUNT]
    velocities = [float(v) for v in joint_state.velocity][:JOINT_COUNT]
    efforts = [float(v) for v in joint_state.effort][:JOINT_COUNT]
    for bucket in (positions, velocities, efforts):
        bucket.extend([0.0] * (JOINT_COUNT - len(bucket)))

    resp = GetState_Response(
        positions=positions,
        velocities=velocities,
        efforts=efforts,
        valid=valid,
        feedback_age_sec=round(age, 3),
        detail=(
            f"关节反馈 {'新鲜' if valid else '已过期'}（age={age:.3f}s, stale>{stale}s）"
            + ("；无末端位姿反馈" if end_pose is None else "")
        ),
    )
    if end_pose is not None:
        resp.x = float(end_pose.position.x)
        resp.y = float(end_pose.position.y)
        resp.z = float(end_pose.position.z)
        resp.qx = float(end_pose.orientation.x)
        resp.qy = float(end_pose.orientation.y)
        resp.qz = float(end_pose.orientation.z)
        resp.qw = float(end_pose.orientation.w)
        resp.detail += f"；末端位姿 age={time.monotonic() - pose_t:.3f}s"
    return resp


# ── 生命周期 ─────────────────────────────────────────────────────────

@service.on_init
def init(cfg: dict):
    """REGISTERED -> INACTIVE：解析配置，不分配重资源。"""
    joint_names = cfg.get("joint_names", list(_state["joint_names"]))
    if not isinstance(joint_names, (list, tuple)) or len(joint_names) != JOINT_COUNT:
        return Err(f"joint_names 需要 {JOINT_COUNT} 个名字，收到 {joint_names!r}")
    _state["joint_names"] = tuple(str(n) for n in joint_names)

    topics = dict(DEFAULT_TOPICS)
    topics.update({k: str(v) for k, v in (cfg.get("topics") or {}).items()})
    for k, v in topics.items():
        if not v.startswith("/"):
            return Err(f"topics.{k} 必须是绝对 ROS 2 话题名，收到 {v!r}")
    _state["topics"] = topics

    _state["dry_run"] = bool(cfg.get("dry_run", False))

    numeric = {
        "feedback_stale_sec": (0.0, False),
        "motion_timeout_sec": (0.0, True),
        "joint_tolerance_rad": (0.0, False),
        "pose_position_tolerance_m": (0.0, False),
        "pose_angle_tolerance_rad": (0.0, False),
    }
    for key, (minimum, allow_zero) in numeric.items():
        default = _state[key]
        try:
            value = float(cfg.get(key, default))
        except (TypeError, ValueError):
            return Err(f"{key} 必须是数字")
        if not math.isfinite(value) or value < minimum or (value == minimum and not allow_zero):
            op = ">=" if allow_zero else ">"
            return Err(f"{key} 必须 {op} 0")
        _state[key] = value

    log.info(
        "init ok: dry_run=%s joint_names=%s stale=%.2fs timeout=%.1fs",
        _state["dry_run"], list(_state["joint_names"]),
        _state["feedback_stale_sec"], _state["motion_timeout_sec"],
    )
    return Ok()


@service.on_activate
def activate():
    """INACTIVE -> ACTIVE：初始化 rclpy 节点与话题 I/O。"""
    try:
        _ensure_ros()
    except Exception as exc:  # noqa: BLE001
        # 不阻塞 boot：注册与 MCP 工具声明继续，工具调用时会再次尝试并返回明确错误。
        log.warning("activate: ROS 2 初始化失败（工具调用会重试）：%s", exc)
    return Ok()


@service.on_deactivate
def deactivate():
    log.info("deactivate: 保留 ROS 2 节点以便重新激活")
    return Ok()


@service.on_shutdown
def shutdown():
    log.info("shutdown: 释放 ROS 2 资源")
    executor = _state.get("executor")
    node = _state.get("node")
    rclpy = _state.get("rclpy")
    if executor is not None:
        try:
            executor.shutdown()
        except Exception:  # noqa: BLE001
            pass
    if node is not None:
        try:
            node.destroy_node()
        except Exception:  # noqa: BLE001
            pass
    if rclpy is not None:
        try:
            rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass
    _state["ros_ready"] = False


if __name__ == "__main__":
    service.run()
