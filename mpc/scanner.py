# mpc/scanner.py
# -*- coding: utf-8 -*-
import os, time, sqlite3, hashlib, json
from typing import List, Tuple, Optional
from web3 import Web3

# 外部依赖：coincurve 用于椭圆曲线点操作；requests 用于调用 MPC 节点
import requests
from coincurve import PrivateKey, PublicKey

# =============================================================================
# 环境配置
# =============================================================================
DB_PATH         = os.getenv("DB_PATH", "mpc_index.db")
USER_ID         = os.getenv("USER_ID", "alice")
TARGET_ADDRESS  = os.getenv("TARGET_ADDRESS", "0x70997970C51812dc3A010C7d01b50e0d17dc79C8")

# 是否启用 MPC（阈值扫描）；true/1/yes 开启
USE_MPC         = os.getenv("USE_MPC", "true").lower() in ("1", "true", "yes")

# MPC 节点列表（逗号分隔），每个节点暴露 /scan_share 接口：POST {"R":"0x..33B"}
# 返回：{"i": <int>, "Yi": "0x02/03..33B"}  其中 Yi = (view_sk_share_i) * R
MPC_NODES       = [x.strip() for x in os.getenv("MPC_NODES", "http://127.0.0.1:7001,http://127.0.0.1:7002,http://127.0.0.1:7003").split(",") if x.strip()]
MPC_THRESHOLD   = int(os.getenv("MPC_THRESHOLD", "2"))  # t-of-n
HTTP_TIMEOUT_S  = float(os.getenv("HTTP_TIMEOUT_S", "1.5"))

# SCAN_CODEC: "x32"（默认，与前端一致），"comp33"（压缩点33B），"auto"（两种都试）
SCAN_CODEC      = os.getenv("SCAN_CODEC", "x32").lower()

# 本地回退需要的 view 私钥（用于无 MPC 或分片不足时的 fallback）
SECP_N = int("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16)

def derive_view_private_key(address: str) -> str:
    addr_lower = address.lower()
    seed_view = Web3.keccak(text=addr_lower + ":view")       # 32B
    seed_int  = int.from_bytes(seed_view, "big")
    view_sk_int = (seed_int % (SECP_N - 1)) + 1              # [1, n-1]
    return f"0x{view_sk_int:064x}"

VIEW_PRIVATE_KEY = derive_view_private_key(TARGET_ADDRESS)

# =============================================================================
# 小工具
# =============================================================================
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
    return x.to_bytes(32, "big")

# =============================================================================
# 本地口径：X(32B) → sha256 → keccak256（与前端保持一致）
# =============================================================================
def _tag_from_shared_x32(R_bytes: bytes, view_sk_hex: str) -> bytes:
    sk = PrivateKey.from_hex(_strip0x(view_sk_hex))
    R  = PublicKey(R_bytes)                          # 33B 压缩公钥（0x02/0x03..）
    shared_pt = R.multiply(sk.secret)
    uncompressed = shared_pt.format(compressed=False)  # 65B: 0x04||X||Y
    x32 = uncompressed[1:33]
    return Web3.keccak(hashlib.sha256(x32).digest())

def _tag_from_shared_comp33(R_bytes: bytes, view_sk_hex: str) -> bytes:
    sk = PrivateKey.from_hex(_strip0x(view_sk_hex))
    R  = PublicKey(R_bytes)
    comp33 = R.multiply(sk.secret).format(compressed=True)   # 33B
    return Web3.keccak(hashlib.sha256(comp33).digest())

def derive_tag_local(R_bytes: bytes, view_sk_hex: str) -> Tuple[bytes, Optional[bytes], str]:
    codec = SCAN_CODEC
    if codec == "x32":
        return _tag_from_shared_x32(R_bytes, view_sk_hex), None, "x32"
    elif codec == "comp33":
        return _tag_from_shared_comp33(R_bytes, view_sk_hex), None, "comp33"
    else:  # auto
        t1 = _tag_from_shared_x32(R_bytes, view_sk_hex)
        t2 = _tag_from_shared_comp33(R_bytes, view_sk_hex)
        return t1, t2, "auto"

# =============================================================================
# 阈值扫描（MPC）：收集 Yi = (share_i) * R（点），用拉格朗日系数在 0 聚合 S = view_sk * R
# 最后取 X(32B) → sha256 → keccak256 生成 tag
# =============================================================================
def _lagrange_coeffs_at_zero(indices: List[int]) -> List[int]:
    """
    计算拉格朗日系数 λ_i(0) over secp256k1 域（mod n）。
    indices 为不重复的正整数（例如 [1,2,4]）。
    """
    lambdas: List[int] = []
    for i in indices:
        num, den = 1, 1
        for j in indices:
            if j == i:
                continue
            num = (num * (-j)) % SECP_N
            den = (den * (i - j)) % SECP_N
        # λ_i = num * den^{-1} mod n
        den_inv = pow(den, SECP_N - 2, SECP_N)  # Fermat since n is prime
        lambdas.append((num * den_inv) % SECP_N)
    return lambdas

def _point_mul(pub: PublicKey, k: int) -> PublicKey:
    # coincurve.PublicKey.multiply 需要 32 字节 big-endian 标量
    return pub.multiply(_int_to_32be(k % SECP_N))

def _point_add(p: Optional[PublicKey], q: PublicKey) -> PublicKey:
    if p is None:
        return q
    # combine_keys 接收 list[PublicKey] 做点加
    return PublicKey.combine_keys([p, q])

def collect_scan_shares(R_bytes: bytes, need: int) -> List[Tuple[int, bytes]]:
    """
    调用 MPC 节点的 /scan_share 接口，收集至少 need 份 (i, Yi_bytes)
    - 请求：POST /scan_share { "R": "0x..." }
    - 响应：{ "i": <int>, "Yi": "0x02/03..33B" }
    """
    shares: List[Tuple[int, bytes]] = []
    payload = {"R": _b2h(R_bytes)}
    for url in MPC_NODES:
        try:
            resp = requests.post(f"{url.rstrip('/')}/scan_share", json=payload, timeout=HTTP_TIMEOUT_S)
            resp.raise_for_status()
            data = resp.json()
            i = int(data["i"])
            Yi = _as_bytes(data["Yi"])
            if len(Yi) != 33 or Yi[0] not in (2, 3):
                print(f"[scanner] ⚠️ bad Yi from {url}: len={len(Yi)}")
                continue
            shares.append((i, Yi))
            if len(shares) >= need:
                break
        except Exception as e:
            print(f"[scanner] ⚠️ share from {url} failed: {e}")
            continue
    return shares

def derive_tag_threshold(R_bytes: bytes) -> Tuple[bytes, Optional[bytes], str]:
    """
    阈值扫描生成 tag：
    - 收集 Yi = (share_i)*R（压缩点33B）
    - 计算 λ_i(0)
    - 聚合 S = sum( λ_i * Yi )
    - codec='x32'：取 X(32B) → sha256 → keccak
      codec='comp33'：取 S.compressed(33B) → sha256 → keccak
      codec='auto'：两种都算，主口径为 x32
    """
    shares = collect_scan_shares(R_bytes, need=MPC_THRESHOLD)
    if len(shares) < MPC_THRESHOLD:
        raise RuntimeError(f"not enough MPC shares: got {len(shares)}/{MPC_THRESHOLD}")

    indices = [i for (i, _) in shares]
    lambdas = _lagrange_coeffs_at_zero(indices)

    # 聚合点 S
    S: Optional[PublicKey] = None
    for lam, (_, Yi_bytes) in zip(lambdas, shares):
        Yi = PublicKey(Yi_bytes)
        lamYi = _point_mul(Yi, lam)
        S = _point_add(S, lamYi)

    if S is None:
        raise RuntimeError("failed to aggregate point S")

    # 计算 tag
    codec = SCAN_CODEC
    if codec == "x32" or codec == "auto":
        uncompressed = S.format(compressed=False)
        x32 = uncompressed[1:33]
        tag_x32 = Web3.keccak(hashlib.sha256(x32).digest())
    else:
        tag_x32 = None

    if codec == "comp33" or codec == "auto":
        comp33 = S.format(compressed=True)
        tag_c33 = Web3.keccak(hashlib.sha256(comp33).digest())
    else:
        tag_c33 = None

    if codec == "x32":
        return tag_x32, None, "mpc:x32"
    elif codec == "comp33":
        return tag_c33, None, "mpc:comp33"
    else:
        return tag_x32, tag_c33, "mpc:auto"

# =============================================================================
# 数据库
# =============================================================================
def ensure_tables():
    con = sqlite3.connect(DB_PATH)
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
    # 幂等：同一 event 只入箱一次
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_inbox_event ON inbox(event_id)")
    con.commit()
    con.close()

def fetch_unscanned() -> List[Tuple]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, tag, R, memo, commitment FROM events WHERE scanned=0")
    rows = cur.fetchall()
    con.close()
    return rows

def mark_scanned(eid: int, matched: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("UPDATE events SET scanned=1, matched=? WHERE id=?", (matched, eid))
    con.commit()
    con.close()

def insert_inbox(user_id: str, eid: int, tag: bytes, R: bytes, memo: bytes, commitment: bytes):
    con = sqlite3.connect(DB_PATH)
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
    ensure_tables()
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
                print(f"[scanner] ⚠️  eid={eid} unexpected R length/prefix: len={len(R_raw)} first={R_raw[:1].hex()}")
                mark_scanned(eid, 0)
                continue

            # 优先走 MPC；失败则回退本地
            if USE_MPC:
                try:
                    tag_primary, tag_secondary, codec_used = derive_tag_threshold(R_raw)
                except Exception as mpc_err:
                    print(f"[scanner] ⚠️ MPC derive failed for eid={eid}: {mpc_err} -> fallback local")
                    tag_primary, tag_secondary, codec_used = derive_tag_local(R_raw, VIEW_PRIVATE_KEY)
                    codec_used = "fallback:" + codec_used
            else:
                tag_primary, tag_secondary, codec_used = derive_tag_local(R_raw, VIEW_PRIVATE_KEY)

            dbg = f"[scanner] eid={eid} R_len={len(R_raw)} codec={codec_used} " \
                  f"tag_db={_b2h(tag_db)} tag_calc={_b2h(tag_primary)}"
            if tag_secondary is not None:
                dbg += f" tag_calc_alt={_b2h(tag_secondary)}"
            print(dbg)

            matched = 0
            if tag_primary == tag_db:
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
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN scanned=0 THEN 1 ELSE 0 END) FROM events")
        total, pending = cur.fetchone()
        print(f"[scanner] DB={os.path.abspath(DB_PATH)} total={total} pending={pending}")
    except Exception:
        pass
    con.close()

def main():
    print(f"🔍 [scanner] Starting scanner for {USER_ID}")
    print(f"🎯 Target address: {TARGET_ADDRESS}")
    print(f"🔑 View private key: {VIEW_PRIVATE_KEY[:10]}... (only used for fallback)")
    print(f"💾 Database: {DB_PATH}")
    print(f"🧮 TAG codec: {SCAN_CODEC} (x32 recommended)")
    print(f"🧩 MPC: {USE_MPC}  nodes={MPC_NODES}  t={MPC_THRESHOLD}")

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
            print(f"❌ [scanner] error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()
