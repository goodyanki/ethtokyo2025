# wallet_light.py (可选)
import sqlite3, os
DB_PATH = os.getenv("DB_PATH", "mpc_index.db")
USER_ID = os.getenv("USER_ID", "alice")

con = sqlite3.connect(DB_PATH); cur = con.cursor()
cur.execute("""
SELECT i.id, hex(i.tag), hex(i.R), i.status, e.txhash, e.block
FROM inbox i
JOIN events e ON i.event_id = e.id
WHERE i.user_id=? ORDER BY i.detected_at DESC
""", (USER_ID,))
rows = cur.fetchall()
con.close()

print("Inbox for", USER_ID)
for r in rows:
    iid, tag_hex, R_hex, status, tx, blk = r
    print(f"- inbox#{iid} [block {blk}] tag={tag_hex[:12]}... R={R_hex[:10]}... status={status} tx={tx}")
