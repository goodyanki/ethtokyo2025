#!/usr/bin/env bash
set -euo pipefail

BASE_ADDR=""
VIEW_SK=""
HOST="127.0.0.1"
P1=7001; P2=7002; P3=7003

die() { echo "Error: $*" >&2; exit 1; }

# 参数解析
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

# 生成 shares
TMPFILE="$(mktemp -t mpcshares.XXXXXX)"
python3 - "$BASE_ADDR" "$VIEW_SK" > "$TMPFILE" <<'PY'
import sys, secrets
from web3 import Web3
N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

def derive_view_sk_from_addr(addr: str) -> int:
    addr = addr.strip()
    if not (addr.startswith(("0x","0X")) and len(addr)==42):
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

S1=""; S2=""; S3=""
while IFS= read -r line; do
  case "$line" in
    1:*) S1="${line#*:}";;
    2:*) S2="${line#*:}";;
    3:*) S3="${line#*:}";;
  esac
done < "$TMPFILE"
rm -f "$TMPFILE"

for n in 1 2 3; do
  v="$(eval echo \$S$n)"
  [[ -z "$v" ]] && die "failed to parse share $n"
  [[ "${v:0:2}" != "0x" || "${#v}" -ne 66 ]] && die "share $n bad format (expect 0x + 64 hex), got: $v"
done

echo "== Derived 2-of-3 shares =="
echo "  1: ${S1:0:6}... (len=${#S1})"
echo "  2: ${S2:0:6}... (len=${#S2})"
echo "  3: ${S3:0:6}... (len=${#S3})"
echo

# 清理旧进程
pkill -f "uvicorn mpc.node_scan:app" >/dev/null 2>&1 || true

start_node () {
  local idx="$1" share="$2" port="$3"
  NODE_INDEX="$idx" VIEW_SK_SHARE_HEX="$share" PYTHONPATH="$PWD" \
    python3 -m uvicorn mpc.node_scan:app \
      --host "$HOST" --port "$port" --no-access-log --log-level warning \
      > "node${idx}.log" 2>&1 &
  echo "node #$idx starting at http://${HOST}:${port} (log: node${idx}.log)"
}

start_node 1 "$S1" "$P1"
start_node 2 "$S2" "$P2"
start_node 3 "$S3" "$P3"

# 健康检查
check_health () {
  local port="$1" name="$2"
  for _ in {1..10}; do
    if curl -s "http://${HOST}:${port}/health" | grep -q '"ok":true'; then
      echo "✅ $name healthy on :$port"; return 0
    fi
    sleep 0.5
  done
  echo "❌ $name not healthy on :$port. See node${name#node }.log"; return 1
}

ok=0
check_health "$P1" "node1" && ok=$((ok+1)) || true
check_health "$P2" "node2" && ok=$((ok+1)) || true
check_health "$P3" "node3" && ok=$((ok+1)) || true
[[ $ok -lt 3 ]] && { echo "Some nodes failed. Tail logs with: tail -n 200 node1.log node2.log node3.log"; exit 1; }

echo
echo "✅ All nodes healthy."
echo "Run scanner with:"
echo "  export USE_MPC=true"
echo "  export MPC_NODES=\"http://${HOST}:${P1},http://${HOST}:${P2},http://${HOST}:${P3}\""
echo "  export MPC_THRESHOLD=2"
echo "  python3 mpc/scanner.py"
