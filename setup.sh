#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# 准备部署 .venv（--system-site-packages，复用 ROS 2 Humble 的 rclpy/消息包）并检查依赖。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ROS_SETUP="${RBNX_ROS_SETUP:-/opt/ros/humble/setup.bash}"
VENV="$ROOT/.venv"
if [[ ! -f "$ROS_SETUP" ]]; then echo "找不到 ROS 2 Humble：$ROS_SETUP" >&2; exit 1; fi
if ! command -v rbnx >/dev/null 2>&1; then echo "找不到 rbnx；请先完成 Robonix 安装并配置 PATH。" >&2; exit 1; fi
if ! rbnx path robonix-api >/dev/null 2>&1; then
  echo "Robonix 源码路径尚未配置；请运行 rbnx setup /path/to/robonix。" >&2
  exit 1
fi
set +u
source "$ROS_SETUP"
set -u
if [[ "${ROS_DISTRO:-}" != "humble" ]]; then echo "当前 ROS_DISTRO=${ROS_DISTRO:-未设置}；此部署要求 ROS 2 Humble。" >&2; exit 1; fi
if [[ ! -x "$VENV/bin/python" ]]; then python3 -m venv --system-site-packages "$VENV"; fi
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"
"$VENV/bin/python" - <<'PYIMPORT'
import geometry_msgs.msg, numpy, rclpy, serial, sensor_msgs.msg, std_msgs.msg, yaml
print("ROS 2、消息类型和 Python 依赖已就绪")
PYIMPORT
printf 'Robonix: '
rbnx --version
echo "Python 环境：$VENV"
