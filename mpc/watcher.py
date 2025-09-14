# mpc/watcher.py
import os, json, sqlite3, time
from web3 import Web3
from web3._utils.events import get_event_data

DB_PATH = os.getenv("DB_PATH", "mpc_index.db")
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
REG_ADDR = os.getenv("REGISTRY_V2")  # 部署后的 StealthRegistryV2 地址

# 修复 ABI 路径 - 匹配实际的文件结构
ABI_PATH = os.getenv("REGISTRY_V2_ABI", "../contracts/out/StealthRegistry.sol/StealthRegistryV2.json")

if not REG_ADDR:
    print("❌ REGISTRY_V2 environment variable not set!")
    print("Please set: export REGISTRY_V2=0xYourContractAddress")
    exit(1)

REG_ADDR = Web3.to_checksum_address(REG_ADDR)

# 加载 ABI
try:
    # 尝试相对路径
    if os.path.exists(ABI_PATH):
        with open(ABI_PATH) as f:
            contract_data = json.load(f)
            abi = contract_data["abi"]
    else:
        # 尝试绝对路径
        abs_path = os.path.join(os.path.dirname(__file__), ABI_PATH)
        with open(abs_path) as f:
            contract_data = json.load(f)
            abi = contract_data["abi"]
    print(f"✅ Loaded ABI from: {ABI_PATH}")
except FileNotFoundError:
    print(f"❌ ABI file not found: {ABI_PATH}")
    print("Make sure contracts are compiled: cd contracts && forge build")
    exit(1)
except Exception as e:
    print(f"❌ Error loading ABI: {e}")
    exit(1)

w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract = w3.eth.contract(address=REG_ADDR, abi=abi)

# 查找 Announce 事件 ABI
evt_abi = None
for item in abi:
    if item.get("type") == "event" and item.get("name") == "Announce":
        evt_abi = item
        break

if not evt_abi:
    print("❌ Announce event ABI not found in contract")
    print("Available events:", [item.get("name") for item in abi if item.get("type") == "event"])
    exit(1)

print(f"✅ Found Announce event ABI")

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
    con.commit()
    con.close()
    print("✅ Database tables ensured")

def get_last_block():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT v FROM meta WHERE k='last_block'")
    result = cur.fetchone()
    con.close()
    return int(result[0]) if result else 0

def set_last_block(h: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("UPDATE meta SET v=? WHERE k='last_block'", (str(h),))
    con.commit()
    con.close()

def save_event(block, txhash, tag_bytes, R_bytes, memo_bytes, commitment_bytes):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
      INSERT INTO events(block, txhash, tag, R, memo, commitment, created_at)
      VALUES(?,?,?,?,?,?, strftime('%s','now'))
    """, (block, txhash, tag_bytes, R_bytes, memo_bytes, commitment_bytes))
    event_id = cur.lastrowid
    con.commit()
    con.close()
    return event_id

def poll_once():
    ensure_db()
    last = get_last_block()
    
    try:
        tip = w3.eth.block_number
    except Exception as e:
        print(f"❌ Failed to get block number: {e}")
        return
        
    from_block = last + 1
    if from_block > tip:
        return

    # Announce 事件的 topic
    topic = w3.keccak(text="Announce(bytes,bytes,bytes32,bytes32)").hex()
    
    try:
        logs = w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": tip,
            "address": REG_ADDR,
            "topics": [topic]
        })
    except Exception as e:
        print(f"❌ Failed to get logs: {e}")
        return

    print(f"📡 Scanning blocks {from_block}-{tip}, found {len(logs)} events")

    for lg in logs:
        try:
            ed = get_event_data(w3.codec, evt_abi, lg)
            R = ed["args"]["R"]                     # bytes
            memo = ed["args"]["memoCipher"]         # bytes
            commitment = ed["args"]["commitment"]   # HexBytes(32)
            tag = ed["args"]["tag"]                 # HexBytes(32)

            event_id = save_event(
                lg["blockNumber"],
                lg["transactionHash"].hex(),
                bytes(tag),
                bytes(R),
                bytes(memo),
                bytes(commitment),
            )
            
            print(f"✅ Saved event #{event_id} from block {lg['blockNumber']}")
            print(f"   - R: {bytes(R).hex()[:20]}...")
            print(f"   - tag: {bytes(tag).hex()[:20]}...")
            
            last = max(last, lg["blockNumber"])
            
        except Exception as e:
            print(f"❌ Error processing log: {e}")
            continue

    set_last_block(tip)

def main():
    print(f"🔄 [watcher] Starting...")
    print(f"📡 RPC: {RPC_URL}")
    print(f"📝 Registry: {REG_ADDR}")
    print(f"💾 Database: {DB_PATH}")
    
    # 检查连接
    try:
        if w3.is_connected():
            chain_id = w3.eth.chain_id
            print(f"⛓️  Connected to chain ID: {chain_id}")
        else:
            print("❌ RPC connection failed")
            return
    except Exception as e:
        print(f"❌ RPC connection error: {e}")
        return
    
    # 检查合约
    try:
        code = w3.eth.get_code(REG_ADDR)
        if code == b"":
            print(f"❌ No contract code at {REG_ADDR}")
            print("Make sure the contract is deployed")
            return
        else:
            print(f"✅ Contract verified at {REG_ADDR}")
    except Exception as e:
        print(f"❌ Error checking contract: {e}")
        return
    
    # 主循环
    print("🚀 Watcher started, monitoring for events...")
    while True:
        try:
            poll_once()
        except KeyboardInterrupt:
            print("\n👋 Watcher stopped")
            break
        except Exception as e:
            print(f"❌ [watcher] error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()