# mpc/scanner.py
import sqlite3, time
from typing import List, Tuple
from mpc_core.threshold_scan import derive_tag_tofn, parse_shares_json

# --- DEMO 配置（直接写在文件里） ---
DB_PATH = "mpc_index.db"
USER_ID = "alice"

# Shamir 分片（示例：t=2 of n=3，选了 1号分片和 3号分片）
# 实际情况每个 MPC 节点只持有自己的分片，这里为了 demo 把 JSON 集中放一起
SHARES_JSON = '[["1","0x1a3f9b7d34d8c6e8..."],["3","0x287ab91c53de9fa2..."]]'
SHARES: List[Tuple[int,int]] = parse_shares_json(SHARES_JSON)

# -------------------------------

def ensure_tables():
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
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
    con.commit(); con.close()

def fetch_unscanned():
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("SELECT id, tag, R, memo, commitment FROM events WHERE scanned=0")
    rows = cur.fetchall()
    con.close()
    return rows

def mark_scanned(eid: int, matched: int):
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("UPDATE events SET scanned=1, matched=? WHERE id=?", (matched, eid))
    con.commit(); con.close()

def insert_inbox(user_id: str, eid: int, tag: bytes, R: bytes, memo: bytes, commitment: bytes):
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("""
      INSERT INTO inbox(user_id, event_id, tag, R, memo, commitment, detected_at)
      VALUES(?,?,?,?,?,?, strftime('%s','now'))
    """, (user_id, eid, tag, R, memo, commitment))
    con.commit(); con.close()

def scan_once():
    ensure_tables()
    pending = fetch_unscanned()
    if not pending:
        return
    for eid, tag_b, R_b, memo_b, commitment_b in pending:
        try:
            tag_prime = derive_tag_tofn(R_b, SHARES)  # t-of-n 计算 tag'
            if tag_prime == tag_b:
                insert_inbox(USER_ID, eid, tag_b, R_b, memo_b, commitment_b)
                mark_scanned(eid, 1)
                print(f"[scanner] MATCH event #{eid} -> inbox[{USER_ID}]")
            else:
                mark_scanned(eid, 0)
        except Exception as e:
            print(f"[scanner] error on event {eid}: {e}")
            mark_scanned(eid, 0)

if __name__ == "__main__":
    print(f"[scanner] user={USER_ID}, shares={SHARES}")
    while True:
        scan_once()
        time.sleep(2)
