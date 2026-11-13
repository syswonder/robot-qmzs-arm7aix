#!/usr/bin/env python3
# SPDX-License-Identifier: MulanPSL-2.0
"""linker_hand_control — 灵巧手姿态 MCP 服务（fist / open）。

把 o6_hand 原语的 `robonix/primitive/hand/move_joint` gRPC 契约包装成
Pilot / `rbnx chat` 可调用的两个 MCP 工具：

  fist  握拳   -> 官方 O6 左手 “握拳” preset  raw [67, 151, 0, 0, 0, 0]
  open  张开   -> 官方 O6 左手 “张开” preset  raw [255, 179, 255, 255, 255, 255]

预设来自 linkerhand-python-sdk 的 LinkerHand/config/O6_positions.yaml。
原语接口的数值是归一化 [0,1] 且位置极性反转（1=闭合，raw 255=张开），
本服务只负责 preset 的 raw -> 归一化换算；CAN 总线仍由 o6_hand 独占。

注意：O6 运动较慢，单帧命令即可接受，但大约需要 10–15 秒才完全到位；
本服务下发两次（间隔 50 ms）确保收到，然后立即返回，不阻塞等待。
"""
from __future__ import annotations

import logging
import threading
import time

from robonix_api import ATLAS, Err, Ok, Service
from robonix_api.atlas_types import Transport

# 必须先在 Service 构造时把 codegen 目录加入 sys.path，再 import 生成模块。
from linker_hand_control_mcp import (
    Fist_Request, Fist_Response,
    Open_Request, Open_Response,
)

service = Service(id="linker_hand_control", namespace="robonix/service/linker_hand_control")

log = logging.getLogger("linker_hand_control")
logging.basicConfig(level=logging.INFO, format="[linker_hand_control] %(levelname)s %(message)s")

MOVE_JOINT_CONTRACT = "robonix/primitive/hand/move_joint"

# O6 控制轴顺序（与 o6_hand 的 info 一致；按名字下发，顺序不敏感）。
AXIS_NAMES = (
    "thumb_cmc_pitch",
    "thumb_cmc_yaw",
    "index_mcp_pitch",
    "middle_mcp_pitch",
    "ring_mcp_pitch",
    "pinky_mcp_pitch",
)

# 官方 preset：raw 0..255，255 = 完全张开。
RAW_OPEN = (255, 179, 255, 255, 255, 255)   # 左手 张开
RAW_FIST = (67, 151, 0, 0, 0, 0)           # 左手 握拳

_state: dict = {
    "lock": threading.Lock(),
    "stub": None,
    "channel": None,
    "grpc_channel": None,
}


def _normalized(raw_values) -> list[float]:
    """raw 0..255 (255=open) -> 契约归一化 [0,1] (1=closed)。"""
    return [round(1.0 - float(value) / 255.0, 6) for value in raw_values]


def _ensure_client():
    """懒连接 o6_hand 原语的 move_joint gRPC 服务，返回 stub。"""
    stub = _state["stub"]
    if stub is not None:
        return stub
    with _state["lock"]:
        if _state["stub"] is not None:
            return _state["stub"]

        import grpc
        import hand_pb2  # noqa: F401  (由 codegen 生成，供 stub 使用)
        import robonix_contracts_pb2_grpc as cg

        caps = ATLAS.find_capability(contract_id=MOVE_JOINT_CONTRACT, transport=Transport.GRPC)
        caps = [cap for cap in caps if cap.provider_kind.name == "PRIMITIVE"]
        if not caps:
            raise RuntimeError("没有可用的 o6_hand primitive（hand/move_joint gRPC）")
        cap = caps[0]

        channel = service.connect_capability(cap, MOVE_JOINT_CONTRACT, Transport.GRPC)
        grpc_channel = grpc.insecure_channel(channel.endpoint)
        stub = cg.RobonixPrimitiveHandMoveJointStub(grpc_channel)

        _state.update({"stub": stub, "channel": channel, "grpc_channel": grpc_channel})
        log.info("connected o6_hand move_joint @ %s", channel.endpoint)
        return stub


def _send_preset(name: str, raw_values) -> tuple[bool, str]:
    try:
        import hand_pb2

        stub = _ensure_client()
        targets = [
            hand_pb2.JointValue(name=axis, value=value)
            for axis, value in zip(AXIS_NAMES, _normalized(raw_values))
        ]
        request = hand_pb2.MoveJoint_Request(targets=targets)

        # O6 接受单帧命令，但重复一次更稳（0.05 s 间隔，不构成“两写者”）。
        last_message = ""
        for _ in range(2):
            resp = stub.MoveJoint(request)
            last_message = resp.message
            if not resp.ok:
                return False, f"o6_hand move_joint 拒绝：{resp.message}"
            time.sleep(0.05)

        log.info("%s preset sent: raw=%s normalized=%s", name, raw_values, _normalized(raw_values))
        return True, (
            f"已下发{('握拳' if name == 'fist' else '张开')}预设（O6 左手 raw={list(raw_values)}）。"
            "O6 运动较慢，大约 10–15 秒到位；请确认手指周围无障碍。"
        )
    except Exception as exc:  # noqa: BLE001 - MCP 工具必须返回错误而不是崩溃
        log.exception("%s 下发失败", name)
        return False, f"下发失败：{exc}"


@service.mcp("robonix/service/linker_hand_control/fist")
async def fist(req: Fist_Request) -> Fist_Response:
    """把灵巧手握拳（O6 左手官方握拳预设）。"""
    ok, message = _send_preset("fist", RAW_FIST)
    return Fist_Response(ok=ok, message=message)


@service.mcp("robonix/service/linker_hand_control/open")
async def open(req: Open_Request) -> Open_Response:
    """把灵巧手张开（O6 左手官方张开预设）。"""
    ok, message = _send_preset("open", RAW_OPEN)
    return Open_Response(ok=ok, message=message)


def main() -> int:
    service.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
