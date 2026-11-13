#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# 从本仓库根目录 source：准备 ROS 2 Humble + 部署 .venv + Robonix 相关环境变量。
# 各个原语/服务包自己的 scripts/start.sh 会再 source 它们需要的运行时环境。
_QMZS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RBNX_ROS_SETUP="${RBNX_ROS_SETUP:-/opt/ros/humble/setup.bash}"
if [[ ! -f "$RBNX_ROS_SETUP" ]]; then
  echo "找不到 ROS 2 环境：$RBNX_ROS_SETUP" >&2
  return 1 2>/dev/null || exit 1
fi
_qmzs_had_nounset=0
case $- in *u*) _qmzs_had_nounset=1 ;; esac
set +u
source "$RBNX_ROS_SETUP"
if [[ "$_qmzs_had_nounset" == "1" ]]; then set -u; fi
unset _qmzs_had_nounset
if [[ "${ROS_DISTRO:-}" != "humble" ]]; then
  echo "当前 ROS_DISTRO=${ROS_DISTRO:-未设置}；此部署要求 ROS 2 Humble。" >&2
  return 1 2>/dev/null || exit 1
fi
if [[ -f "$_QMZS_ROOT/.venv/bin/activate" ]]; then source "$_QMZS_ROOT/.venv/bin/activate"; fi
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export RMW_IMPLEMENTATION="${ROBONIX_RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"
export ROBONIX_DEPLOY_DIR="$_QMZS_ROOT"
export ROBONIX_MANIFEST="${ROBONIX_MANIFEST:-$_QMZS_ROOT/robonix_manifest.yaml}"
export RBNX_ROS_SETUP
export RBNX_PYTHON="$_QMZS_ROOT/.venv/bin/python"
export RBNX_CODEGEN_PYTHON="$RBNX_PYTHON"
export LINKERHAND_O6_PYTHON="${LINKERHAND_O6_PYTHON:-$RBNX_PYTHON}"
export HAND_GESTURE_PYTHON="${HAND_GESTURE_PYTHON:-$RBNX_PYTHON}"
