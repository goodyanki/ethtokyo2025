# improved_test_wallet.py
import sqlite3, os, time
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "mpc_index.db")
USER_ID = os.getenv("USER_ID", "alice")

def show_wallet_status():
    """显示钱包状态"""
    print(f"\n=== 钱包状态 - {USER_ID} ===")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # 检查收件箱
    cur.execute("""
    SELECT i.id, hex(i.tag), hex(i.R), i.status, e.txhash, e.block, i.detected_at
    FROM inbox i
    JOIN events e ON i.event_id = e.id
    WHERE i.user_id=? ORDER BY i.detected_at DESC LIMIT 10
    """, (USER_ID,))
    
    inbox_rows = cur.fetchall()
    
    if inbox_rows:
        print(f"\n📬 收件箱 ({len(inbox_rows)} 条):")
        for r in inbox_rows:
            iid, tag_hex, R_hex, status, tx, blk, detected = r
            detected_time = datetime.fromtimestamp(int(detected)).strftime('%H:%M:%S')
            print(f"  {iid:2d} | {detected_time} | 区块{blk:6d} | {status:8s} | tag:{tag_hex[:12]}... | {tx[:10]}...")
    else:
        print("\n📭 收件箱为空")
    
    # 检查链上事件总数
    cur.execute("SELECT COUNT(*), MAX(block) FROM events")
    event_count, latest_block = cur.fetchone()
    print(f"\n📡 链上事件: {event_count or 0} 条, 最新区块: {latest_block or 'N/A'}")
    
    # 检查扫描状态
    cur.execute("SELECT COUNT(*) FROM events WHERE scanned=1")
    scanned_count = cur.fetchone()[0]
    print(f"🔍 已扫描: {scanned_count or 0} 条")
    
    con.close()

def watch_mode():
    """实时监控模式"""
    print("🔄 启动实时监控模式 (Ctrl+C 退出)")
    try:
        while True:
            show_wallet_status()
            print("\n" + "="*60)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n👋 监控已停止")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "watch":
        watch_mode()
    else:
        show_wallet_status()
        print("\n💡 使用 'python test_wallet.py watch' 启动实时监控")