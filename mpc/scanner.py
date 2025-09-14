# mpc/scanner.py
# -*- coding: utf-8 -*-
"""
MPC 阈值扫描器（2-of-3 示例，阈值/节点数可配）
- 从 SQLite 的 events 表取未扫描事件
- 对每条事件里的 R（压缩33B公钥）做“阈值 ECDH”：
    收集 Yi = (share_i) * R（从 MPC 节点获取），按 λ_i(0) 聚合得到 S = v * R
- 生成 tag（默认 X32 -> sha256 -> keccak），与事件中 tag 比对，命中则入 inbox

依赖：pip install web3 requests coincurve
Python: 3.8+

环境变量（可选）：
  DB_PATH=mpc_index.db
  USER_ID=alice
  TARGET_ADDRESS=0x7099...  # 仅用于 fallback 本地 view_sk 派生
  VIEW_SK_HEX=0x...         # 显式指定 view_sk（优先于 TARGET_ADDRESS 派生）
  USE_MPC=true|false        # 是否启用 MPC（默认 true）
  MPC_NODES=http://127.0.0.1:7001,http://127.0.0.1:7002,http://127.0.0.1:7003
  MPC_THRESHOLD=2
  HTTP_TIMEOUT_S=1.5
  MPC_AUTH=shared-secret     # 与节点共享的鉴权秘密；节点侧验 keccak(auth||R)
  SCAN_CODEC=x32|comp33|auto # tag 口径（默认 x32，auto 会两种都算）
  STRICT_MPC=false           # 严格要求 MPC；不足阈值时不回退本地
  LOOP_INTERVAL_S=2          # 扫描轮询间隔秒
"""
import os
import time
import sqlite3
import hashlib
from typing import List, Tuple, Optional

import requests
from web3 import Web3
from coincurve import PrivateKey, PublicKey

# =============================================================================
# 环境配置
# =============================================================================
DB_PATH         = os.getenv("DB_PATH", "mpc_index.db")
USER_ID         = os.getenv("USER_ID", "alice")
TARGET_ADDRESS  = os.getenv("TARGET_ADDRESS", "0x70997970C51812dc3A010C7d01b50e0d17dc79C8")
VIEW_SK_HEX_ENV = os.getenv("VIEW_SK_HEX", "").strip()

USE_MPC         = os.getenv("USE_MPC", "true").lower() in ("1", "true", "yes")
MPC_NODES       = [x.strip() for x in os.getenv("MPC_NODES", "http://127.0.0.1:7001,http://127.0.0.1:7002,http://127.0.0.1:7003").split(",") if x.strip()]
MPC_THRESHOLD   = int(os.getenv("MPC_THRESHOLD", "2"))
HTTP_TIMEOUT_S  = float(os.getenv("HTTP_TIMEOUT_S", "1.5"))
MPC_AUTH        = os.getenv("MPC_AUTH", "").encode("utf-8")

SCAN_CODEC      = os.getenv("SCAN_CODEC", "x32").lower()  # x32|comp33|auto
STRICT_MPC      = os.getenv("STRICT_MPC", "false").lower() in ("1", "true", "yes")
LOOP_INTERVAL_S = float(os.getenv("LOOP_INTERVAL_S", "2"))

SECP_N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

def _strip0x(s: str) -> str:
    return s[2:] if isinstance(s, str) and s.lower().startswith("0x") else s

def _b2h(b: bytes) -> str:
    return "0x" + b.hex()

def _as_bytes(x) -> bytes:
    if x is None:
        return b""
    if isinstance(x, (bytes, bytearray)):
        return bytes(x)
    if isinstance(x, memoryview):
        return bytes(x)
    if isinstance(x, str):
        s = x.strip()
        if s.lower().startswith("0x"):
            s = s[2:]
        try:
            return bytes.fromhex(s)
        except Exception:
            return s.encode("utf-8", "ignore")
    try:
        return bytes(x)
    except Exception:
        return b""

def _int_to_32be(x: int) -> bytes:
    return (x % SECP_N).to_bytes(32, "big")

def derive_view_private_key_from_addr(address: str) -> str:
    """演示/开发用：从地址派生 view_sk（不要用于生产）"""
    addr_lower = address.lower()
    seed_view = Web3.keccak(text=addr_lower + ":view")  # 32B
    seed_int  = int.from_bytes(seed_view, "big")
    view_sk_int = (seed_int % (SECP_N - 1)) + 1         # [1, n-1]
    return f"0x{view_sk_int:064x}"

VIEW_PRIVATE_KEY = VIEW_SK_HEX_ENV if VIEW_SK_HEX_ENV else derive_view_private_key_from_addr(TARGET_ADDRESS)

# =============================================================================
# TAG 计算口径
# =============================================================================
def _tag_from_shared_x32(R_bytes: bytes, view_sk_hex: str) -> bytes:
    sk = PrivateKey.from_hex(_strip0x(view_sk_hex))
    R  = PublicKey(R_bytes)
    shared = R.multiply(sk.secret)                      # 共有点 vR
    uncompressed = shared.format(compressed=False)      # 65B = 0x04 || X || Y
    x32 = uncompressed[1:33]
    return Web3.keccak(hashlib.sha256(x32).digest())

def _tag_from_shared_comp33(R_bytes: bytes, view_sk_hex: str) -> bytes:
    sk = PrivateKey.from_hex(_strip0x(view_sk_hex))
    R  = PublicKey(R_bytes)
    comp33 = R.multiply(sk.secret).format(compressed=True)
    return Web3.keccak(hashlib.sha256(comp33).digest())

def derive_tag_local(R_bytes: bytes, view_sk_hex: str) -> Tuple[bytes, Optional[bytes], str]:
    codec = SCAN_CODEC
    if codec == "x32":
        return _tag_from_shared_x32(R_bytes, view_sk_hex), None, "local:x32"
    elif codec == "comp33":
        return _tag_from_shared_comp33(R_bytes, view_sk_hex), None, "local:comp33"
    else:  # auto
        t1 = _tag_from_shared_x32(R_bytes, view_sk_hex)
        t2 = _tag_from_shared_comp33(R_bytes, view_sk_hex)
        return t1, t2, "local:auto"

# =============================================================================
# 阈值 ECDH
# =============================================================================
def _lagrange_coeffs_at_zero(indices: List[int]) -> List[int]:
    """计算拉格朗日系数 λ_i(0) over secp256k1 标量域（mod n）"""
    lambdas: List[int] = []
    for i in indices:
        num = 1
        den = 1
        for j in indices:
            if j == i:
                continue
            num = (num * (-j % SECP_N)) % SECP_N
            den = (den * ((i - j) % SECP_N)) % SECP_N
        den_inv = pow(den, SECP_N - 2, SECP_N)  # n 为素数，费马小定理求逆
        lambdas.append((num * den_inv) % SECP_N)
    return lambdas

def _point_mul(pub: PublicKey, k: int) -> PublicKey:
    return pub.multiply(_int_to_32be(k))

def _point_add(p: Optional[PublicKey], q: PublicKey) -> PublicKey:
    if p is None:
        return q
    return PublicKey.combine_keys([p, q])

def collect_scan_shares(R_bytes: bytes, need: int) -> List[Tuple[int, bytes]]:
    """
    调用各 MPC 节点 /scan_share，收集至少 need 份不同索引的 (i, Yi)
    请求：POST { "R": "0x..33B", "auth": "0xkeccak(auth||R)" }（auth 可选）
    响应：{ "i": <int>, "Yi": "0x02/03..33B" }
    """
    shares: List[Tuple[int, bytes]] = []
    seen = set()
    auth_sig = Web3.keccak(MPC_AUTH + R_bytes).hex() if MPC_AUTH else None
    payload = {"R": _b2h(R_bytes)}
    if auth_sig:
        payload["auth"] = auth_sig

    for url in MPC_NODES:
        try:
            resp = requests.post(f"{url.rstrip('/')}/scan_share", json=payload, timeout=HTTP_TIMEOUT_S)
            resp.raise_for_status()
            data = resp.json()
            i = int(data["i"])
            if i in seen:
                continue
            Yi = _as_bytes(data["Yi"])
            # 基本健全性：压缩点 33B，首字节 0x02/0x03；on-curve 校验由构造 PublicKey 触发
            if len(Yi) != 33 or Yi[0] not in (2, 3):
                print(f"[scanner] ⚠️ bad Yi from {url}: len={len(Yi)} head={Yi[:1].hex()}")
                continue
            PublicKey(Yi)  # 无异常代表在曲线上
            shares.append((i, Yi))
            seen.add(i)
            if len(shares) >= need:
                break
        except Exception as e:
            print(f"[scanner] ⚠️ share from {url} failed: {e}")
            continue
    return shares

def derive_tag_threshold(R_bytes: bytes) -> Tuple[bytes, Optional[bytes], str]:
    """MPC 阈值计算 tag；返回 (主口径tag, 备选tag或None, 说明)"""
    shares = collect_scan_shares(R_bytes, need=MPC_THRESHOLD)
    if len(shares) < MPC_THRESHOLD:
        raise RuntimeError(f"not enough MPC shares: got {len(shares)}/{MPC_THRESHOLD}")

    indices = [i for (i, _) in shares]
    lambdas = _lagrange_coeffs_at_zero(indices)

    # 聚合 S = Σ λ_i * Yi
    S: Optional[PublicKey] = None
    for lam, (_, Yi_bytes) in zip(lambdas, shares):
        Yi = PublicKey(Yi_bytes)
        lamYi = _point_mul(Yi, lam)
        S = _point_add(S, lamYi)

    if S is None:
        raise RuntimeError("failed to aggregate point S")

    codec = SCAN_CODEC
    tag_x32 = None
    tag_c33 = None
    if codec in ("x32", "auto"):
        uncompressed = S.format(compressed=False)
        x32 = uncompressed[1:33]
        tag_x32 = Web3.keccak(hashlib.sha256(x32).digest())
    if codec in ("comp33", "auto"):
        comp33 = S.format(compressed=True)
        tag_c33 = Web3.keccak(hashlib.sha256(comp33).digest())

    if codec == "x32":
        return tag_x32, None, "mpc:x32"
    elif codec == "comp33":
        return tag_c33, None, "mpc:comp33"
    else:
        return tag_x32, tag_c33, "mpc:auto"

# =============================================================================
# SQLite 存取
# =============================================================================
def _open_db():
    con = sqlite3.connect(DB_PATH)
    # 稳定性：WAL 模式，适合读多写少
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return con

def ensure_tables():
    con = _open_db()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      block INTEGER,
      txhash TEXT,
      tag BLOB,
      R   BLOB,
      memo BLOB,
      commitment BLOB,
      scanned INTEGER DEFAULT 0,
      matched INTEGER DEFAULT 0,
      created_at INTEGER
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inbox(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT,
      event_id INTEGER,
      tag BLOB,
      R   BLOB,
      memo BLOB,
      commitment BLOB,
      status TEXT DEFAULT 'unread',
      detected_at INTEGER
    )""")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_inbox_event ON inbox(event_id)")
    con.commit()
    con.close()

def fetch_unscanned() -> List[Tuple]:
    con = _open_db()
    cur = con.cursor()
    cur.execute("SELECT id, tag, R, memo, commitment FROM events WHERE scanned=0")
    rows = cur.fetchall()
    con.close()
    return rows

def mark_scanned(eid: int, matched: int):
    con = _open_db()
    cur = con.cursor()
    cur.execute("UPDATE events SET scanned=1, matched=? WHERE id=?", (matched, eid))
    con.commit()
    con.close()

def insert_inbox(user_id: str, eid: int, tag: bytes, R: bytes, memo: bytes, commitment: bytes):
    con = _open_db()
    cur = con.cursor()
    cur.execute("""
      INSERT OR IGNORE INTO inbox(user_id, event_id, tag, R, memo, commitment, detected_at)
      VALUES(?,?,?,?,?,?, strftime('%s','now'))
    """, (user_id, eid, tag, R, memo, commitment))
    con.commit()
    con.close()

# =============================================================================
# 扫描一次
# =============================================================================
def scan_once():
    pending = fetch_unscanned()
    if not pending:
        print("[scanner] no pending events")
        return

    for eid, tag_b, R_b, memo_b, commitment_b in pending:
        tag_db = _as_bytes(tag_b)
        R_raw  = _as_bytes(R_b)
        memo_b = _as_bytes(memo_b) if memo_b is not None else b""
        commitment_b = _as_bytes(commitment_b) if commitment_b is not None else b""

        try:
            if len(R_raw) != 33 or R_raw[0] not in (2, 3):
                print(f"[scanner] ⚠️  eid={eid} unexpected R length/prefix: len={len(R_raw)} head={R_raw[:1].hex()}")
                mark_scanned(eid, 0)
                continue

            # 优先 MPC；若 STRICT_MPC=true，MPC 失败时不会回退本地
            used_codec = ""
            tag_primary: Optional[bytes] = None
            tag_secondary: Optional[bytes] = None

            if USE_MPC:
                try:
                    tag_primary, tag_secondary, used_codec = derive_tag_threshold(R_raw)
                except Exception as mpc_err:
                    if STRICT_MPC:
                        print(f"[scanner] ❌ MPC required but failed for eid={eid}: {mpc_err}")
                        mark_scanned(eid, 0)
                        continue
                    print(f"[scanner] ⚠️ MPC derive failed for eid={eid}: {mpc_err} -> fallback local")
                    tag_primary, tag_secondary, used_codec = derive_tag_local(R_raw, VIEW_PRIVATE_KEY)
            else:
                tag_primary, tag_secondary, used_codec = derive_tag_local(R_raw, VIEW_PRIVATE_KEY)

            dbg = f"[scanner] eid={eid} codec={used_codec} " \
                  f"tag_db={_b2h(tag_db)} tag_calc={_b2h(tag_primary or b'')}"
            if tag_secondary is not None:
                dbg += f" tag_calc_alt={_b2h(tag_secondary)}"
            print(dbg)

            matched = 0
            if tag_primary is not None and tag_primary == tag_db:
                matched = 1
            elif tag_secondary is not None and tag_secondary == tag_db:
                matched = 1

            if matched:
                insert_inbox(USER_ID, eid, tag_db, R_raw, memo_b, commitment_b)
                mark_scanned(eid, 1)
                print(f"[scanner] ✅ MATCH event #{eid} -> inbox[{USER_ID}]")
            else:
                mark_scanned(eid, 0)
                print(f"[scanner] ❌ No match event #{eid}")

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[scanner] error on event {eid}: {e}")
            mark_scanned(eid, 0)

# =============================================================================
# 主程序
# =============================================================================
def _debug_print_pending():
    con = _open_db()
    cur = con.cursor()
    try:
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN scanned=0 THEN 1 ELSE 0 END) FROM events")
        row = cur.fetchone()
        total = row[0] if row and row[0] is not None else 0
        pending = row[1] if row and row[1] is not None else 0
        print(f"[scanner] DB={os.path.abspath(DB_PATH)} total={total} pending={pending}")
    except Exception:
        pass
    con.close()

def main():
    print(f"🔍 [scanner] Starting scanner for user: {USER_ID}")
    print(f"🎯 Target address: {TARGET_ADDRESS}")
    print(f"🔑 View SK (fallback): {VIEW_PRIVATE_KEY[:10]}... (only used when MPC disabled/insufficient)")
    print(f"💾 Database: {os.path.abspath(DB_PATH)}")
    print(f"🧮 TAG codec: {SCAN_CODEC} (x32 recommended; auto will try both)")
    print(f"🧩 MPC: {USE_MPC}  nodes={MPC_NODES}  t={MPC_THRESHOLD}  strict={STRICT_MPC}")
    print(f"🔐 Auth: {'enabled' if MPC_AUTH else 'disabled'}")

    ensure_tables()
    _debug_print_pending()

    print("🚀 Scanner started, monitoring for matching events...")
    while True:
        try:
            scan_once()
        except KeyboardInterrupt:
            print("\n👋 Scanner stopped")
            break
        except Exception as e:
            print(f"❌ [scanner] loop error: {e}")
        time.sleep(LOOP_INTERVAL_S)

if __name__ == "__main__":
    main()
