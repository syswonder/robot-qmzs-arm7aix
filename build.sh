#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# 构建整机部署：把清单里的原语/服务/技能拉取到 rbnx-boot/cache 并 codegen/colcon 构建。
# 首次会 clone 并编译 vendored OrbbecSDK_ROS2（耗时较长，一次即可）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ -f "$ROOT/.env" ]]; then set -a; source "$ROOT/.env"; set +a; fi
source "$ROOT/ros2_env.sh"
# 构建期清掉已 source 的 ROS 覆盖层：它会 shadow /opt/ros 的标准消息包
# （例如 sensor_msgs 不带 colcon 目标），导致 vendored OrbbecSDK_ROS2 编译失败。
# 每个包的 scripts/build.sh 自己会 source /opt/ros/humble，构建阶段不需要覆盖层。
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
if [[ ! -x "$RBNX_PYTHON" ]]; then echo "Python 环境缺失；先运行 ./setup.sh" >&2; exit 1; fi
if ! command -v rbnx >/dev/null 2>&1; then echo "找不到 rbnx；请检查 Robonix 安装和 PATH。" >&2; exit 1; fi
manifest="${ROBONIX_MANIFEST:-$ROOT/robonix_manifest.yaml}"
if [[ "$manifest" != /* ]]; then manifest="$ROOT/$manifest"; fi
if [[ ! -f "$manifest" ]]; then echo "Robonix 清单不存在：$manifest" >&2; exit 1; fi
export ROBONIX_MANIFEST="$manifest"
exec rbnx build -f "$manifest" "$@"
