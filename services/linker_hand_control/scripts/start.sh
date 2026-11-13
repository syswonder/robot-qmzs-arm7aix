#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
# 启动 linker_hand_control：注册 MCP 工具，按需通过 atlas 连接 o6_hand 原语。
set -eo pipefail
PKG_ROOT="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG_ROOT"

export PYTHONPATH="$(rbnx path robonix-api):$PKG_ROOT:${PYTHONPATH:-}"
# 部署环境里 RBNX_PYTHON 指向 .venv/bin/python（含 grpcio/mcp）。
PY="${RBNX_PYTHON:-python3}"
exec "$PY" -m linker_hand_control.main
