#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# 启动本整机部署：加载 .env → ROS 2 环境 → 设备预检 → 起 Zenoh router → rbnx boot。
#
# 设备独占（三项都只能有一个进程持有）：
#   - arm7aix_controller：U2CAN 串口，默认 /dev/ttyACM0（ARM7AIX_SERIAL_PORT 可覆盖）
#   - o6_hand：CAN 接口，默认 can2（LINKERHAND_CAN_IFACE 可覆盖）
#   - orbbec_camera：Orbbec 相机（libuvc 拿不到会一直重试）
# 同机的 handeye-calibration 标定网页会占用串口与相机，boot 会失败；先把它停掉。
# 确认安全时可用 SKIP_DEVICE_PREFLIGHT=1 跳过串口/相机占用检查。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 本机私有配置（VLM 凭据等）；rbnx boot 需要从环境变量展开 ${VLM_*}。
if [[ -f "$ROOT/.env" ]]; then set -a; source "$ROOT/.env"; set +a; fi
source "$ROOT/ros2_env.sh"

manifest="${ROBONIX_MANIFEST:-$ROOT/robonix_manifest.yaml}"
if [[ "$manifest" != /* ]]; then manifest="$ROOT/$manifest"; fi
if [[ ! -f "$manifest" ]]; then echo "Robonix 清单不存在：$manifest" >&2; exit 1; fi
export ROBONIX_MANIFEST="$manifest"
if [[ ! -x "$RBNX_PYTHON" ]]; then echo "Python 环境缺失；先运行 ./setup.sh" >&2; exit 1; fi
if ! command -v rbnx >/dev/null 2>&1; then echo "找不到 rbnx；请检查 PATH。" >&2; exit 1; fi

# ── 串口预检 ────────────────────────────────────────────────────────
device="${ARM7AIX_SERIAL_PORT:-/dev/ttyACM0}"
if [[ ! -c "$device" ]]; then
  echo "U2CAN 串口不存在：$device" >&2
  ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true
  echo "确认适配器已插好；设备名不同时用 ARM7AIX_SERIAL_PORT=/dev/ttyACM1 ./start.sh。" >&2
  exit 1
fi
if [[ ! -r "$device" || ! -w "$device" ]]; then
  echo "当前用户没有串口读写权限：$device" >&2
  ls -l "$device" >&2
  echo '加入 dialout 组并重新登录：sudo usermod -aG dialout "$USER"' >&2
  exit 1
fi

# ── CAN 预检（灵巧手）───────────────────────────────────────────────
can_iface="${LINKERHAND_CAN_IFACE:-can2}"
if [[ ! -e "/sys/class/net/$can_iface" ]]; then
  echo "CAN 接口不存在：$can_iface" >&2
  echo "先接好 XCAN-USB/CAN 适配器并拉起接口：" >&2
  echo "  sudo ip link set $can_iface type can bitrate 1000000 && sudo ip link set $can_iface up" >&2
  echo "接口名不同时用 LINKERHAND_CAN_IFACE=can0 ./start.sh（并同步改清单里的 can_iface）。" >&2
  exit 1
fi
can_state="$(cat "/sys/class/net/$can_iface/operstate" 2>/dev/null || echo down)"
if [[ "$can_state" != "up" ]]; then
  echo "CAN 接口未 up：$can_iface（state=$can_state）" >&2
  echo "  sudo ip link set $can_iface type can bitrate 1000000 && sudo ip link set $can_iface up" >&2
  exit 1
fi

# ── 设备占用预检 ────────────────────────────────────────────────────
if [[ "${SKIP_DEVICE_PREFLIGHT:-0}" != "1" ]]; then
  conflicts=()
  if command -v fuser >/dev/null 2>&1 && fuser -s "$device" 2>/dev/null; then
    holders="$(fuser "$device" 2>/dev/null | tr -s ' ' | sed 's/^ *//')"
    conflicts+=("串口 $device 已被进程占用（PID: ${holders:-?}）")
  fi
  if command -v pgrep >/dev/null 2>&1; then
    procs="$(pgrep -af 'orbbec_camera|gemini_330_series|dabai_dcw' 2>/dev/null | head -5 || true)"
    [[ -n "$procs" ]] && conflicts+=("已有 Orbbec 相机驱动进程在运行：\n${procs}")
    procs="$(pgrep -af 'handeye-calibration/.*manage\.py' 2>/dev/null | head -5 || true)"
    [[ -n "$procs" ]] && conflicts+=("手眼标定程序在运行：\n${procs}")
  fi
  if (( ${#conflicts[@]} > 0 )); then
    echo "检测到设备冲突：本次 boot 会失败（原语各自要独占串口、CAN 与相机）。" >&2
    printf '  - %b\n' "${conflicts[@]}" >&2
    echo "" >&2
    echo "停掉占用进程后重试；确认没有残留（下面命令应无输出）：" >&2
    echo "  pgrep -af 'orbbec_camera|manage.py'" >&2
    echo "确认安全时可设 SKIP_DEVICE_PREFLIGHT=1 跳过本检查。" >&2
    exit 1
  fi
fi

router_pid=""
stack_started=0
run_dir="$ROOT/.run"
mkdir -p "$run_dir"
cleanup() {
  status=$?
  trap - EXIT INT TERM
  if [[ "$stack_started" == "1" ]]; then rbnx shutdown -f "$manifest" >/dev/null 2>&1 || true; fi
  if [[ -n "$router_pid" ]]; then
    kill -TERM "$router_pid" 2>/dev/null || true
    wait "$router_pid" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
router_ready() {
  "$RBNX_PYTHON" - <<'PYPORT'
import socket
try:
    with socket.create_connection(("127.0.0.1", 7447), timeout=0.25): pass
except OSError:
    raise SystemExit(1)
PYPORT
}
if [[ "$RMW_IMPLEMENTATION" == "rmw_zenoh_cpp" ]] && ! router_ready; then
  prefix="$(ros2 pkg prefix rmw_zenoh_cpp 2>/dev/null || true)"
  router_bin="${ROBONIX_ZENOH_ROUTER_BIN:-$prefix/lib/rmw_zenoh_cpp/rmw_zenohd}"
  if [[ ! -x "$router_bin" ]]; then
    echo "找不到 rmw_zenohd：$router_bin" >&2
    echo "请安装 Humble 的 rmw_zenoh_cpp，或设置 ROBONIX_ZENOH_ROUTER_BIN。" >&2
    exit 1
  fi
  "$router_bin" >"$run_dir/rmw_zenohd.log" 2>&1 &
  router_pid=$!
  for _ in $(seq 1 40); do
    if router_ready; then break; fi
    if ! kill -0 "$router_pid" 2>/dev/null; then tail -80 "$run_dir/rmw_zenohd.log" >&2 || true; exit 1; fi
    sleep 0.25
  done
  if ! router_ready; then echo "rmw_zenohd 未在 10 秒内监听 127.0.0.1:7447。" >&2; exit 1; fi
fi

echo "启动 Robonix：$manifest"
echo "U2CAN 串口：$device"
echo "CAN 接口：$can_iface"
stack_started=1
rbnx boot -v -f "$manifest" "$@"
