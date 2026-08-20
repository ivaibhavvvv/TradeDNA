import sqlite3

conn = sqlite3.connect("tradedna_dev.db")
cursor = conn.cursor()

# Query all devices and ensure account_sync_states exists
devices = cursor.execute("SELECT account_number, tenant_id, broker, server_name, currency, trade_mode, last_seen_at FROM devices").fetchall()
for dev in devices:
    acc_num, tenant_id, broker, server_name, currency, trade_mode, last_seen = dev
    cursor.execute("""
        INSERT OR IGNORE INTO account_sync_states (
            account_number, tenant_id, broker, server_name, currency, trade_mode,
            sync_status, current_cursor_time_msc, current_cursor_deal_ticket,
            last_successful_sync_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'CONNECTED', 0, 0, ?, datetime('now'), datetime('now'))
    """, (acc_num, tenant_id, broker or "EXNESS", server_name or "Exness", currency or "USD", trade_mode or "DEMO", last_seen or "2026-08-20 00:00:00"))

conn.commit()
print("Updated Account Sync States:")
for row in cursor.execute("SELECT account_number, tenant_id, sync_status, last_successful_sync_at FROM account_sync_states").fetchall():
    print(row)
conn.close()
