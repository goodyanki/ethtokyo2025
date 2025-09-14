# mpc/server.py
from fastapi import FastAPI
import sqlite3
from typing import List, Dict, Any
from fastapi.middleware.cors import CORSMiddleware


DB_PATH = "mpc_index.db"

app = FastAPI(title="MPC Wallet Server")

def fetch_inbox(user_id: str) -> List[Dict[str, Any]]:
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
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

@app.get("/wallet/sync")
def wallet_sync(user_id: str = "alice"):
    """
    拉取用户收件箱中的交易（已经通过 scanner 命中的）
    """
    inbox = fetch_inbox(user_id)
    return {"user": user_id, "inbox": inbox}

@app.post("/wallet/decrypt")
def wallet_decrypt(inbox_id: int, user_id: str = "alice"):
    """
    演示解密：真实情况应使用 view 私钥协作解密 ECIES 密文。
    这里先 mock，返回 memo 里存的 hex。
    """
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("""
    SELECT e.memo
    FROM inbox i JOIN events e ON i.event_id = e.id
    WHERE i.id=? AND i.user_id=?
    """, (inbox_id, user_id))
    row = cur.fetchone(); con.close()
    if not row:
        return {"ok": False, "error": "not found"}
    memo_hex = row[0].hex()
    # TODO: 替换为真正的 ECIES 解密
    return {"ok": True, "plaintext": memo_hex}

@app.post("/stealth/spend")
def stealth_spend(inbox_id: int, to: str, amount: int, user_id: str = "alice"):
    """
    演示花费：真实情况应使用 TSS ECDSA 对交易签名并广播。
    这里先 mock，返回一个虚拟 txid。
    """
    # TODO: 接入 TSS 模块，构造 raw tx，并用阈值签名
    fake_txid = f"0xDEMOFAKETX{inbox_id:04d}"
    return {"ok": True, "txid": fake_txid, "to": to, "amount": amount}

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 或 ["*"] 直接全开
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}