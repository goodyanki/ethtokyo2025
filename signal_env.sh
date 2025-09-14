#!/usr/bin/env bash
# signal_env.sh - 为“Signal 路”配置环境并可一键启动 watcher & scanner
# 依赖：bash、python3；（可选）jq（--auto 解析 Foundry broadcast 需要）
set -euo pipefail

# ========= 默认配置（可通过参数覆盖） =========
RPC_URL_DEFAULT="http://127.0.0.1:8545"
DB_DEFAULT="mpc_signal.db"
NODES_DEFAULT="http://127.0.0.1:7001,http://127.0.0.1:7002,http://127.0.0.1:7003"
THRESH_DEFAULT="2"
AUTH_DEFAULT=""          # HMAC 鉴权共享密钥（留空为关闭）
CODEC_DEFAULT="x32"      # x32 | comp33 | auto
STRICT_DEFAULT="false"   # true 则 MPC 不足不回退
LOOP_DEFAULT="2"
TIMEOUT_DEFAULT="1.5"
USER_DEFAULT="alice"
TARGET_DEFAULT="0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
VIEW_SK_DEFAULT=""

# 路径默认指向 Desktop/project/mpc
WATCHER_PY_DEFAULT="$HOME/Desktop/project/mpc/watcher.py"
SCANNER_PY_DEFAULT="$HOME/Desktop/project/mpc/scanner.py"
ABI_DEFAULT="$HOME/Desktop/project/contracts/out/SignalBoard.sol/SignalBoard.json"
BROADCAST_DIR_DEFAULT="$HOME/Desktop/project/contracts/broadcast/DeployAndEmit.s.sol"

# ========= 帮助 =========
usage() {
  cat <<'EOF'
用法:
  signal_env.sh export [选项]     # 输出 export 语句（可 eval 到当前 shell）
  signal_env.sh print  [选项]     # 打印将设定的值（不导出不启动）
  signal_env.sh up     [选项]     # 导出并后台启动 watcher + scanner
  signal_env.sh down               # 停止 watcher + scanner
  signal_env.sh status             # 查看运行状态
  signal_env.sh --help             # 帮助

常用选项:
  --rpc URL                 RPC（默认 http://127.0.0.1:8545）
  --addr 0x...              SignalBoard 地址；或用 --auto 自动解析
  --auto                    从 Foundry broadcast 解析 SignalBoard 地址（需 jq）
  --broadcast-subdir PATH   Foundry broadcast 根（默认 ~/Desktop/project/contracts/broadcast/DeployAndEmit.s.sol）
  --db FILE                 SQLite 路径（默认 mpc_signal.db）
  --abi PATH                SignalBoard ABI（默认 ~/Desktop/project/contracts/out/SignalBoard.sol/SignalBoard.json）
  --nodes CSV               MPC 节点列表（默认 7001,7002,7003）
  --threshold N             MPC 阈值（默认 2）
  --auth SECRET             MPC HMAC 鉴权共享密钥
  --codec x32|comp33|auto   tag 口径（默认 x32）
  --strict true|false       严格 MPC（默认 false）
  --loop SECONDS            轮询间隔（默认 2）
  --timeout SECONDS         HTTP 超时（默认 1.5）
  --user ID                 inbox user_id（默认 alice）
  --target 0x...            TARGET_ADDRESS（回退派生用）
  --view-sk 0x...           显式 VIEW_SK_HEX（优先于 target 派生）
  --watcher PATH            watcher.py 路径（默认 ~/Desktop/project/mpc/watcher.py）
  --scanner PATH            scanner.py 路径（默认 ~/Desktop/project/mpc/scanner.py）

示例：
  # 自动解析地址并启动服务
  bash scripts/signal_env.sh up --auto

  # 手动指定地址，仅导出环境变量到当前 shell
  eval "$(bash scripts/signal_env.sh export --addr 0xYourSignalBoard --rpc http://127.0.0.1:8545 --db mpc_signal.db)"
EOF
}

# ========= 解析子命令 =========
CMD="${1:-}"
if [[ -z "${CMD}" || "${CMD}" == "--help" || "${CMD}" == "-h" ]]; then usage; exit 0; fi
shift || true

# ========= 参数默认值 =========
RPC_URL="$RPC_URL_DEFAULT"
SIGNAL_ADDR=""
AUTO_ADDR="false"
BROADCAST_DIR="$BROADCAST_DIR_DEFAULT"
DB_PATH="$DB_DEFAULT"
ABI_PATH="$ABI_DEFAULT"
MPC_NODES="$NODES_DEFAULT"
MPC_THRESHOLD="$THRESH_DEFAULT"
MPC_AUTH="$AUTH_DEFAULT"
SCAN_CODEC="$CODEC_DEFAULT"
STRICT_MPC="$STRICT_DEFAULT"
LOOP_INTERVAL_S="$LOOP_DEFAULT"
HTTP_TIMEOUT_S="$TIMEOUT_DEFAULT"
USER_ID="$USER_DEFAULT"
TARGET_ADDRESS="$TARGET_DEFAULT"
VIEW_SK_HEX="$VIEW_SK_DEFAULT"
WATCHER_PY="$WATCHER_PY_DEFAULT"
SCANNER_PY="$SCANNER_PY_DEFAULT"

# ========= 解析选项 =========
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rpc) RPC_URL="$2"; shift 2 ;;
    --addr) SIGNAL_ADDR="$2"; shift 2 ;;
    --auto) AUTO_ADDR="true"; shift 1 ;;
    --broadcast-subdir) BROADCAST_DIR="$2"; shift 2 ;;
    --db) DB_PATH="$2"; shift 2 ;;
    --abi) ABI_PATH="$2"; shift 2 ;;
    --nodes) MPC_NODES="$2"; shift 2 ;;
    --threshold) MPC_THRESHOLD="$2"; shift 2 ;;
    --auth) MPC_AUTH="$2"; shift 2 ;;
    --codec) SCAN_CODEC="$2"; shift 2 ;;
    --strict) STRICT_MPC="$2"; shift 2 ;;
    --loop) LOOP_INTERVAL_S="$2"; shift 2 ;;
    --timeout) HTTP_TIMEOUT_S="$2"; shift 2 ;;
    --user) USER_ID="$2"; shift 2 ;;
    --target) TARGET_ADDRESS="$2"; shift 2 ;;
    --view-sk) VIEW_SK_HEX="$2"; shift 2 ;;
    --watcher) WATCHER_PY="$2"; shift 2 ;;
    --scanner) SCANNER_PY="$2"; shift 2 ;;
    *) echo "未知参数: $1"; usage; exit 1 ;;
  esac
done

# ========= 工具函数 =========
resolve_addr_from_broadcast() {
  local dir="$1"
  local addr=""
  if ! command -v jq >/dev/null 2>&1; then
    echo ""
    return 0
  fi
  local latest_json
  latest_json="$(ls -t "${dir}"/**/run-latest.json 2>/dev/null | head -n1 || true)"
  if [[ -n "$latest_json" && -f "$latest_json" ]]; then
    addr="$(jq -r '[.transactions[] | select(.transactionType=="CREATE" and .contractName=="SignalBoard")][-1].contractAddress // empty' "$latest_json")"
  fi
  echo "$addr"
}

emit_exports() {
  cat <<EOF
# ---- Signal 路（watcher）----
export DB_PATH="${DB_PATH}"
export RPC_URL="${RPC_URL}"
export REGISTRY_V2="${SIGNAL_ADDR}"
export REGISTRY_V2_ABI="${ABI_PATH}"

# ---- 扫描器（scanner）----
export USER_ID="${USER_ID}"
export TARGET_ADDRESS="${TARGET_ADDRESS}"
export VIEW_SK_HEX="${VIEW_SK_HEX}"
export USE_MPC="true"
export MPC_NODES="${MPC_NODES}"
export MPC_THRESHOLD="${MPC_THRESHOLD}"
export HTTP_TIMEOUT_S="${HTTP_TIMEOUT_S}"
export MPC_AUTH="${MPC_AUTH}"
export SCAN_CODEC="${SCAN_CODEC}"
export STRICT_MPC="${STRICT_MPC}"
export LOOP_INTERVAL_S="${LOOP_INTERVAL_S}"
EOF
}

print_values() {
  cat <<EOF
DB_PATH=${DB_PATH}
RPC_URL=${RPC_URL}
REGISTRY_V2=${SIGNAL_ADDR}
REGISTRY_V2_ABI=${ABI_PATH}
USER_ID=${USER_ID}
TARGET_ADDRESS=${TARGET_ADDRESS}
VIEW_SK_HEX=${VIEW_SK_HEX:-<empty>}
USE_MPC=true
MPC_NODES=${MPC_NODES}
MPC_THRESHOLD=${MPC_THRESHOLD}
HTTP_TIMEOUT_S=${HTTP_TIMEOUT_S}
MPC_AUTH=$( [[ -n "$MPC_AUTH" ]] && echo "<set>" || echo "<empty>" )
SCAN_CODEC=${SCAN_CODEC}
STRICT_MPC=${STRICT_MPC}
LOOP_INTERVAL_S=${LOOP_INTERVAL_S}
Watcher Py: ${WATCHER_PY}
Scanner Py: ${SCANNER_PY}
EOF
}

start_services() {
  mkdir -p "$(dirname "$DB_PATH")" >/dev/null 2>&1 || true
  mkdir -p logs >/dev/null 2>&1 || true

  # 自动解析地址
  if [[ "$AUTO_ADDR" == "true" && -z "$SIGNAL_ADDR" ]]; then
    SIGNAL_ADDR="$(resolve_addr_from_broadcast "$BROADCAST_DIR")"
  fi
  if [[ -z "$SIGNAL_ADDR" ]]; then
    echo "❌ 需要 SignalBoard 地址。用 --addr 指定，或 --auto 自动解析（需 jq）。"
    exit 1
  fi

  # 路径存在校验
  [[ -f "$WATCHER_PY" ]] || { echo "❌ 找不到 watcher: $WATCHER_PY"; exit 1; }
  [[ -f "$SCANNER_PY" ]] || { echo "❌ 找不到 scanner: $SCANNER_PY"; exit 1; }

  # 导出环境到当前进程环境，使子进程可见
  eval "$(emit_exports)"

  echo "▶ 启动 watcher … 日志：logs/watcher_signal.log"
  nohup python3 "$WATCHER_PY" > logs/watcher_signal.log 2>&1 & echo $! > logs/watcher_signal.pid

  echo "▶ 启动 scanner  … 日志：logs/scanner_signal.log"
  nohup python3 "$SCANNER_PY" > logs/scanner_signal.log 2>&1 & echo $! > logs/scanner_signal.pid

  echo "✅ 已启动"
  status_services
}

stop_pid_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local pid
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ -n "${pid}" && -e "/proc/$pid" ]] || ps -p "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 0.2
      if ps -p "$pid" >/dev/null 2>&1; then
        kill -9 "$pid" >/dev/null 2>&1 || true
      fi
      echo "🛑 已停止 PID $pid（来自 $file）"
    fi
    rm -f "$file"
  fi
}

status_services() {
  for name in watcher_signal scanner_signal; do
    if [[ -f "logs/${name}.pid" ]]; then
      pid="$(cat logs/${name}.pid 2>/dev/null || true)"
      if [[ -n "${pid}" && ( -e "/proc/$pid" || $(ps -p "$pid" >/dev/null 2>&1; echo $?) -eq 0 ) ]]; then
        echo "✅ ${name} 运行中 (PID ${pid})"
      else
        echo "⚠️  ${name} 未在运行（stale pid 文件）"
      fi
    else
      echo "ℹ️  ${name} 未启动"
    fi
  done
}

# ========= 执行子命令 =========
case "$CMD" in
  export)
    # 若需要自动解析地址也支持
    if [[ "$AUTO_ADDR" == "true" && -z "$SIGNAL_ADDR" ]]; then
      SIGNAL_ADDR="$(resolve_addr_from_broadcast "$BROADCAST_DIR")"
    fi
    if [[ -z "$SIGNAL_ADDR" ]]; then
      echo "❌ 需要 SignalBoard 地址（--addr 或 --auto）。" >&2
      exit 1
    fi
    emit_exports
    ;;
  print)
    if [[ "$AUTO_ADDR" == "true" && -z "$SIGNAL_ADDR" ]]; then
      SIGNAL_ADDR="$(resolve_addr_from_broadcast "$BROADCAST_DIR")"
    fi
    print_values
    ;;
  up)
    start_services
    ;;
  down)
    stop_pid_file "logs/watcher_signal.pid"
    stop_pid_file "logs/scanner_signal.pid"
    ;;
  status)
    status_services
    ;;
  *)
    echo "未知子命令: $CMD"
    usage
    exit 1
    ;;
esac
