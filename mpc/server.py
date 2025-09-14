# mpc/server.py
import os
import json
import sqlite3
from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3

# 配置
DB_PATH = os.getenv("DB_PATH", "mpc_index.db")
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
REGISTRY_ADDRESS = os.getenv("REGISTRY_V2")  # StealthRegistry 合约地址
PRIVATE_KEY = os.getenv("SENDER_PRIVATE_KEY", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")  # 默认 Anvil 私钥

app = FastAPI(title="MPC Wallet Server")

# CORS 设置
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Web3 连接
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# 加载合约 ABI（如果存在的话）
registry_abi = None
registry_contract = None

try:
    abi_path = os.path.join(os.path.dirname(__file__), "../contracts/out/StealthRegistry.sol/StealthRegistryV2.json")
    with open(abi_path) as f:
        contract_data = json.load(f)
        registry_abi = contract_data["abi"]
    
    if REGISTRY_ADDRESS and registry_abi:
        registry_contract = w3.eth.contract(
            address=Web3.to_checksum_address(REGISTRY_ADDRESS), 
            abi=registry_abi
        )
except FileNotFoundError:
    print("Warning: StealthRegistry ABI file not found. Deploy contracts first or set REGISTRY_V2 address.")
except Exception as e:
    print(f"Warning: Failed to load contract: {e}")

# 请求模型
class AnnounceRequest(BaseModel):
    R: str
    tag: str
    memoCipher: Any = None
    commitment: str
    txHash: str = None

# 工具函数
def fetch_inbox(user_id: str) -> List[Dict[str, Any]]:
    """获取用户收件箱"""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("""
        SELECT i.id, e.block, e.txhash, hex(e.tag), hex(e.R), hex(e.memo), hex(e.commitment), i.status
        FROM inbox i
        JOIN events e ON i.event_id = e.id
        WHERE i.user_id=?
        ORDER BY i.detected_at DESC
        """, (user_id,))
        rows = cur.fetchall()
        con.close()
        
        results = []
        for row in rows:
            if row:  # 确保行不为空
                iid, blk, tx, tag_hex, R_hex, memo_hex, commit_hex, status = row
                results.append({
                    "inbox_id": iid,
                    "block": blk,
                    "txhash": tx,
                    "tag": tag_hex,
                    "R": R_hex,
                    "memo": memo_hex,
                    "commitment": commit_hex,
                    "status": status,
                })
        return results
    except Exception as e:
        print(f"Error fetching inbox: {e}")
        return []

# API 端点
@app.get("/health")
def health():
    """健康检查"""
    return {
        "ok": True,
        "rpc_connected": w3.is_connected(),
        "registry_loaded": registry_contract is not None,
        "registry_address": REGISTRY_ADDRESS
    }

@app.get("/wallet/sync")
def wallet_sync(user_id: str = "alice"):
    """拉取用户收件箱中的交易（已经通过 scanner 命中的）"""
    inbox = fetch_inbox(user_id)
    return {"user": user_id, "inbox": inbox}

@app.post("/wallet/decrypt")
def wallet_decrypt(inbox_id: int, user_id: str = "alice"):
    """演示解密：真实情况应使用 view 私钥协作解密 ECIES 密文"""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("""
        SELECT e.memo
        FROM inbox i JOIN events e ON i.event_id = e.id
        WHERE i.id=? AND i.user_id=?
        """, (inbox_id, user_id))
        row = cur.fetchone()
        con.close()
        
        if not row:
            return {"ok": False, "error": "not found"}
        
        memo_hex = row[0].hex() if row[0] else ""
        return {"ok": True, "plaintext": memo_hex}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/stealth/spend")
def stealth_spend(inbox_id: int, to: str, amount: int, user_id: str = "alice"):
    """演示花费：真实情况应使用 TSS ECDSA 对交易签名并广播"""
    fake_txid = f"0xDEMOFAKETX{inbox_id:04d}"
    return {"ok": True, "txid": fake_txid, "to": to, "amount": amount}

@app.post("/sender/announce")
def sender_announce(request: AnnounceRequest):
    """接收发送方的公告请求"""
    try:
        # 如果合约可用，发布到链上
        if registry_contract and REGISTRY_ADDRESS:
            # 准备参数
            R_bytes = bytes.fromhex(request.R[2:] if request.R.startswith('0x') else request.R)
            tag_bytes32 = bytes.fromhex(request.tag[2:] if request.tag.startswith('0x') else request.tag)
            commitment_bytes32 = bytes.fromhex(request.commitment[2:] if request.commitment.startswith('0x') else request.commitment)
            memo_bytes = b""  # 暂时为空
            
            # 构建交易
            account = w3.eth.account.from_key(PRIVATE_KEY)
            
            # 调用 publish 方法
            tx = registry_contract.functions.publish(
                R_bytes,
                memo_bytes, 
                commitment_bytes32,
                tag_bytes32
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 200000,
                'gasPrice': w3.to_wei('10', 'gwei')
            })
            
            # 签名并发送
            signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            return {
                "ok": True,
                "message": "公告已上链",
                "txHash": receipt.transactionHash.hex(),
                "blockNumber": receipt.blockNumber
            }
        else:
            # 合约不可用时，模拟保存到数据库
            print(f"收到公告请求: R={request.R[:10]}..., tag={request.tag[:10]}..., txHash={request.txHash}")
            
            # 模拟写入 events 表
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            
            # 确保 events 表存在
            cur.execute("""
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              block INTEGER,
              txhash TEXT,
              tag BLOB,
              R BLOB,
              memo BLOB,
              commitment BLOB,
              scanned INTEGER DEFAULT 0,
              matched INTEGER DEFAULT 0,
              created_at INTEGER
            )""")
            
            # 插入模拟事件
            tag_bytes = bytes.fromhex(request.tag[2:] if request.tag.startswith('0x') else request.tag)
            R_bytes = bytes.fromhex(request.R[2:] if request.R.startswith('0x') else request.R)
            commitment_bytes = bytes.fromhex(request.commitment[2:] if request.commitment.startswith('0x') else request.commitment)
            memo_bytes = b""  # 暂时为空
            
            cur.execute("""
              INSERT INTO events(block, txhash, tag, R, memo, commitment, created_at)
              VALUES(?,?,?,?,?,?, strftime('%s','now'))
            """, (999999, request.txHash or "0xMOCKTX", tag_bytes, R_bytes, memo_bytes, commitment_bytes))
            
            con.commit()
            con.close()
            
            return {
                "ok": True, 
                "message": "公告已模拟提交（合约未部署）", 
                "mockTxHash": request.txHash or "0xMOCKTX"
            }
        
    except Exception as e:
        print(f"公告处理错误: {e}")
        return {"ok": False, "error": str(e)}

# 启动信息
@app.on_event("startup")
async def startup_event():
    print(f"🚀 MPC Wallet Server starting...")
    print(f"📡 RPC: {RPC_URL}")
    print(f"🔗 Registry: {REGISTRY_ADDRESS or 'Not set'}")
    print(f"📊 Database: {DB_PATH}")
    
    if w3.is_connected():
        chain_id = w3.eth.chain_id
        print(f"⛓️  Connected to chain ID: {chain_id}")
    else:
        print("❌ RPC connection failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)