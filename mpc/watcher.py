# mpc/watcher.py
# -*- coding: utf-8 -*-
import os, json, sqlite3, time
from web3 import Web3
from web3._utils.events import get_event_data

# -------------------- .env 加载（优先 python-dotenv；无则用内置解析） --------------------
def _load_dotenv():
    # 尝试 python-dotenv
    try:
        from dotenv import load_dotenv, find_dotenv  # type: ignore
        # 在 CWD 或其上层查找；找不到就用脚本目录
        path = find_dotenv(usecwd=True)
        if not path:
            here = os.path.dirname(os.path.abspath(__file__))
            cand = os.path.join(here, ".env")
            if os.path.exists(cand):
                path = cand
        if path:
            load_dotenv(path)
            print(f"🧩 .env loaded from: {path}")
            return
    except Exception:
        pass

    # 轻量内置解析（当前目录 / 脚本目录）
    for base in [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]:
        p = os.path.join(base, ".env")
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    os.environ.setdefault(k, v)
            print(f"🧩 .env loaded from: {p}")
            return
        except Exception:
            continue

_load_dotenv()

# -------------------- 环境变量（按你的命名） --------------------
# 必填
RPC_URL = os.getenv("envRPC_URL", "http://127.0.0.1:8545")
DB_PATH = os.getenv("DB_PATH", "mpc_index.db")

# 合约地址优先取 SINGNALBOARD（按你给的拼写），其次 SIGNALBOARD，再退 REGISTRY_V2/CONTRACT_ADDR
_CONTRACT_ADDR_RAW = (
    os.getenv("SINGNALBOARD")
    or os.getenv("SIGNALBOARD")
    or os.getenv("REGISTRY_V2")
    or os.getenv("CONTRACT_ADDR")
)

if not _CONTRACT_ADDR_RAW:
    print("❌ CONTRACT address not set.\n请在 .env 中设置 SINGNALBOARD=0x...（或 SIGNALBOARD/REGISTRY_V2）")
    raise SystemExit(1)

try:
    CONTRACT_ADDR = Web3.to_checksum_address(_CONTRACT_ADDR_RAW)
except Exception:
    print(f"❌ 非法地址: { _CONTRACT_ADDR_RAW }")
    raise SystemExit(1)

# ABI 路径：SIGNALBOARD_ABI 优先，其次 REGISTRY_V2_ABI/CONTRACT_ABI，最后内置最小 ABI
ABI_PATH = (
    os.getenv("SIGNALBOARD_ABI")
    or os.getenv("REGISTRY_V2_ABI")
    or os.getenv("CONTRACT_ABI")
)

# -------------------- 读取 ABI（或使用内置） --------------------
abi = None
if ABI_PATH and os.path.exists(os.path.expanduser(ABI_PATH)):
    ABI_PATH = os.path.expanduser(ABI_PATH)
    try:
        with open(ABI_PATH, "r") as f:
            artifact = json.load(f)
            abi = artifact.get("abi", artifact)
    except Exception as e:
        print(f"⚠️ 读取 ABI 失败（{ABI_PATH}）：{e}，回退到内置最小 ABI")
        abi = None

if abi is None:
    # 内置最小 ABI（兼容 SignalBoard 与 StealthRegistryV2）
    abi = [
        {
            "type":"event","name":"Signal","anonymous":False,
            "inputs":[
                {"indexed":True,"name":"rx","type":"bytes32"},
                {"indexed":False,"name":"yParity","type":"bool"},
                {"indexed":True,"name":"tag","type":"bytes32"},
                {"indexed":False,"name":"memo","type":"bytes"}
            ]
        },
        {
            "type":"event","name":"Announce","anonymous":False,
            "inputs":[
                {"indexed":False,"name":"R","type":"bytes"},
                {"indexed":False,"name":"memoCipher","type":"bytes"},
                {"indexed":True,"name":"commitment","type":"bytes32"},
                {"indexed":True,"name":"tag","type":"bytes32"}
            ]
        }
    ]
    ABI_PATH = "<<built-in>>"

w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract = w3.eth.contract(address=CONTRACT_ADDR, abi=abi)

# 选择事件：优先 Signal，其次 Announce
evt_abi = None
evt_kind = None  # "signal" | "announce"
for item in abi:
    if item.get("type") == "event" and item.get("name") == "Signal":
        evt_abi = item; evt_kind = "signal"; break
if not evt_abi:
    for item in abi:
        if item.get("type") == "event" and item.get("name") == "Announce":
            evt_abi = item; evt_kind = "announce"; break
if not evt_abi:
    print("❌ ABI 中未找到 Signal/Announce 事件"); raise SystemExit(1)

print(f"✅ Using event: {evt_abi['name']} ({evt_kind})")

# -------------------- DB helpers --------------------
def _open_db():
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return con

def ensure_db():
    con = _open_db(); cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS meta(
        k TEXT PRIMARY KEY,
        v TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS events(
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
    cur.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('last_block','0')")
    con.commit(); con.close()
    print(f"✅ Database ready @ {os.path.abspath(DB_PATH)}")

def get_last_block() -> int:
    con = _open_db(); cur = con.cursor()
    cur.execute("SELECT v FROM meta WHERE k='last_block'")
    row = cur.fetchone(); con.close()
    return int(row[0]) if row else 0

def set_last_block(h: int):
    con = _open_db(); cur = con.cursor()
    cur.execute("UPDATE meta SET v=? WHERE k='last_block'", (str(h),))
    con.commit(); con.close()

def insert_event(block, txhash, R_bytes, tag_bytes, memo_bytes, commitment_bytes):
    con = _open_db(); cur = con.cursor()
    cur.execute("""
      INSERT INTO events(block, txhash, tag, R, memo, commitment, created_at)
      VALUES(?,?,?,?,?,?, strftime('%s','now'))
    """, (block, txhash, tag_bytes, R_bytes, memo_bytes, commitment_bytes))
    eid = cur.lastrowid
    con.commit(); con.close()
    return eid

def _pack_R_from_rx(rx: bytes, y_parity: bool) -> bytes:
    return (b'\x03' if y_parity else b'\x02') + rx

# -------------------- 主轮询 --------------------
def poll_once():
    ensure_db()
    last = get_last_block()

    tip = w3.eth.block_number
    if last >= tip:
        return

    if evt_kind == "signal":
        topic0 = w3.keccak(text="Signal(bytes32,bool,bytes32,bytes)").hex()
    else:
        topic0 = w3.keccak(text="Announce(bytes,bytes,bytes32,bytes32)").hex()

    start = last + 1
    end   = min(tip, start + 4095)

    try:
        logs = w3.eth.get_logs({
            "fromBlock": start,
            "toBlock": end,
            "address": CONTRACT_ADDR,
            "topics": [topic0]
        })
    except Exception as e:
        print(f"❌ get_logs failed: {e}")
        return

    if logs:
        print(f"📡 blocks {start}-{end}: {len(logs)} {evt_kind} event(s)")

    for lg in logs:
        try:
            ed = get_event_data(w3.codec, evt_abi, lg)
            if evt_kind == "signal":
                rx       = ed["args"]["rx"]
                yParity  = ed["args"]["yParity"]
                tag      = ed["args"]["tag"]
                memo     = ed["args"]["memo"]
                R_bytes  = _pack_R_from_rx(bytes(rx), bool(yParity))
                commit_b = b""
            else:
                R_bytes  = bytes(ed["args"]["R"])
                memo     = bytes(ed["args"]["memoCipher"])
                commit_b = bytes(ed["args"]["commitment"])
                tag      = ed["args"]["tag"]

            eid = insert_event(
                lg["blockNumber"], lg["transactionHash"].hex(),
                R_bytes, bytes(tag), memo, commit_b
            )
            print(f"✅ saved event #{eid} @ block {lg['blockNumber']}  R={R_bytes[:2].hex()}.. tag={bytes(tag).hex()[:10]}..")
        except Exception as e:
            print(f"❌ decode/save error: {e}")

    set_last_block(end)

def main():
    print("🔄 [watcher] starting…")
    print(f"⛓️  RPC: {RPC_URL}")
    print(f"📍 Contract: {CONTRACT_ADDR}")
    print(f"📄 ABI: {ABI_PATH}")

    try:
        if not w3.is_connected():
            print("❌ RPC not connected"); return
        code = w3.eth.get_code(CONTRACT_ADDR)
        if code == b"":
            print("❌ No contract code at address"); return
        print("✅ chain_id:", w3.eth.chain_id)
    except Exception as e:
        print("❌ RPC check error:", e); return

    print("🚀 watcher running…")
    while True:
        try:
            poll_once()
        except KeyboardInterrupt:
            print("\n👋 watcher stopped"); break
        except Exception as e:
            print("❌ loop error:", e)
        time.sleep(1.5)

if __name__ == "__main__":
    main()
