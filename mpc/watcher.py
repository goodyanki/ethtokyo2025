# mpc/watcher.py
import os, json, sqlite3, time
from web3 import Web3
from web3._utils.events import get_event_data

DB_PATH = os.getenv("DB_PATH", "mpc_index.db")
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
REG_ADDR = os.getenv("REGISTRY_V2")  # 部署后的 StealthRegistryV2 地址
ABI_PATH = os.getenv("REGISTRY_V2_ABI", "artifacts/contracts/src/StealthRegistryV2.sol/StealthRegistryV2.json")

if not REG_ADDR:
    raise SystemExit("REGISTRY_V2 not set")
REG_ADDR = Web3.to_checksum_address(REG_ADDR)

with open(ABI_PATH) as f:
    abi = json.load(f)["abi"]

w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract = w3.eth.contract(address=REG_ADDR, abi=abi)

# 抓到 Announce 事件 ABI
evt_abi = None
for item in abi:
    if item.get("type") == "event" and item.get("name") == "Announce":
        evt_abi = item
        break
assert evt_abi, "Announce event ABI not found"

def ensure_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS meta(
      k TEXT PRIMARY KEY,
      v TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      block INTEGER,
      txhash TEXT,
      tag BLOB,            -- bytes32
      R   BLOB,            -- 33B 压缩 secp256k1 公钥
      memo BLOB,           -- 任意长度密文
      commitment BLOB,     -- bytes32
      scanned INTEGER DEFAULT 0,
      matched INTEGER DEFAULT 0,
      created_at INTEGER
    );
    """)
    cur.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('last_block','0')")
    con.commit(); con.close()

def get_last_block():
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("SELECT v FROM meta WHERE k='last_block'")
    (v,) = cur.fetchone()
    con.close()
    return int(v)

def set_last_block(h: int):
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("UPDATE meta SET v=? WHERE k='last_block'", (str(h),))
    con.commit(); con.close()

def save_event(block, txhash, tag_bytes, R_bytes, memo_bytes, commitment_bytes):
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("""
      INSERT INTO events(block, txhash, tag, R, memo, commitment, created_at)
      VALUES(?,?,?,?,?,?, strftime('%s','now'))
    """, (block, txhash, tag_bytes, R_bytes, memo_bytes, commitment_bytes))
    con.commit(); con.close()

def poll_once():
    ensure_db()
    last = get_last_block()
    tip = w3.eth.block_number
    from_block = last + 1
    if from_block > tip:
        return

    topic = w3.keccak(text="Announce(bytes,bytes,bytes32,bytes32)").hex()
    logs = w3.eth.get_logs({
        "fromBlock": from_block,
        "toBlock": tip,
        "address": REG_ADDR,
        "topics": [topic]
    })

    for lg in logs:
        ed = get_event_data(w3.codec, evt_abi, lg)
        R = ed["args"]["R"]                     # bytes
        memo = ed["args"]["memoCipher"]         # bytes
        commitment = ed["args"]["commitment"]   # HexBytes(32)
        tag = ed["args"]["tag"]                 # HexBytes(32)

        save_event(
            lg["blockNumber"],
            lg["transactionHash"].hex(),
            bytes(tag),
            bytes(R),
            bytes(memo),
            bytes(commitment),
        )
        last = max(last, lg["blockNumber"])

    set_last_block(tip)

if __name__ == "__main__":
    print(f"[watcher] RPC={RPC_URL}, registry={REG_ADDR}")
    ensure_db()
    while True:
        try:
            poll_once()
        except Exception as e:
            print("[watcher] error:", e)
        time.sleep(2)
