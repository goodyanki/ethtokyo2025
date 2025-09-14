#!/usr/bin/env bash
set -euo pipefail

# 用法：
#   1) 从基础地址推导 view_sk：
#      ./run_nodes.sh --base-addr 0x70997970C51812dc3A010C7d01b50e0d17dc79C8
#   2) 或直接传入 view_sk（32字节hex）：
#      ./run_nodes.sh --view-sk 0x<64-hex>
#
# 依赖：python3、fastapi、uvicorn、coincurve、web3
# 安装：pip install fastapi uvicorn coincurve web3

BASE_ADDR=""
VIEW_SK=""
HOST="127.0.0.1"
P1=7001; P2=7002; P3=7003

die() { echo "Error: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-addr) BASE_ADDR="${2:-}"; shift 2 ;;
    --view-sk)   VIEW_SK="${2:-}"; shift 2 ;;
    --host)      HOST="${2:-}"; shift 2 ;;
    --p1)        P1="${2:-}"; shift 2 ;;
    --p2)        P2="${2:-}"; shift 2 ;;
    --p3)        P3="${2:-}"; shift 2 ;;
    *) die "unknown arg: $1" ;;
  esac
done

[[ -z "$BASE_ADDR" && -z "$VIEW_SK" ]] && die "must pass --view-sk OR --base-addr"
[[ -n "$BASE_ADDR" && -n "$VIEW_SK" ]] && die "pass only one of --view-sk or --base-addr"
[[ -f "mpc/node_scan.py" ]] || die "mpc/node_scan.py not found (run from repo root)"

# 生成 shares 的临时文件
TMPFILE="$(mktemp -t mpcshares.XXXXXX)"
cleanup() { rm -f "$TMPFILE"; }
trap cleanup EXIT

# 用 Python 派生 view_sk（如果传 base-addr）并做 2-of-3 Shamir
python3 - "$BASE_ADDR" "$VIEW_SK" > "$TMPFILE" <<'PY'
import sys, secrets
from web3 import Web3
N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

def derive_view_sk_from_addr(addr: str) -> int:
    addr = addr.strip()
    if not addr.startswith(("0x","0X")) or len(addr) != 42:
        raise SystemExit("invalid base address")
    seed = Web3.keccak(text=addr.lower() + ":view")
    x = int.from_bytes(seed, "big")
    return (x % (N - 1)) + 1

def shamir_split(secret: int, t: int, n: int):
    a1 = secrets.randbelow(N-1) + 1  # t=2 => f(x)=secret + a1*x
    return [(i, (secret + a1*i) % N) for i in range(1, n+1)]

base_addr = sys.argv[1].strip()
view_sk_hex = sys.argv[2].strip()

if base_addr:
    s = derive_view_sk_from_addr(base_addr)
else:
    h = view_sk_hex[2:] if view_sk_hex.lower().startswith("0x") else view_sk_hex
    if len(h) != 64: raise SystemExit("view_sk must be 32 bytes hex")
    s = int(h, 16)
    if not (1 <= s < N): raise SystemExit("view_sk out of range")

shares = shamir_split(s, t=2, n=3)
for i, y in shares:
    print(f"{i}:0x{y:064x}")
PY

# 解析输出
S1=""; S2=""; S3=""
while IFS= read -r line; do
  case "$line" in
    1:*) S1="${line#*:}";;
    2:*) S2="${line#*:}";;
    3:*) S3="${line#*:}";;
  esac
done < "$TMPFILE"

[[ -z "$S1" || -z "$S2" || -z "$S3" ]] && die "failed to parse shares (check python deps and inputs)"

echo "== Derived 2-of-3 shares =="
echo "  1: $S1"
echo "  2: $S2"
echo "  3: $S3"
echo

# 先杀掉旧的 uvicorn 节点（如果有）
pkill -f "uvicorn mpc.node_scan:app" >/dev/null 2>&1 || true

start_node () {
  local idx="$1" share="$2" port="$3"
  NODE_INDEX="$idx" VIEW_SK_SHARE_HEX="$share" \
    python3 -m uvicorn mpc.node_scan:app --host "$HOST" --port "$port" --reload \
    > "node${idx}.log" 2>&1 &
  echo "node #$idx started at http://${HOST}:${port} (log: node${idx}.log)"
}

start_node 1 "$S1" "$P1"
start_node 2 "$S2" "$P2"
start_node 3 "$S3" "$P3"

echo
echo "✅ All nodes started."
echo "Check:"
echo "  curl http://${HOST}:${P1}/health"
echo "  curl http://${HOST}:${P2}/health"
echo "  curl http://${HOST}:${P3}/health"
echo
echo "Run scanner with:"
echo "  export USE_MPC=true"
echo "  export MPC_NODES=\"http://${HOST}:${P1},http://${HOST}:${P2},http://${HOST}:${P3}\""
echo "  export MPC_THRESHOLD=2"
echo "  python mpc/scanner.py"
