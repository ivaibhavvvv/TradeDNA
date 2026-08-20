import sqlite3
import os
import glob

# 1. Clean Database Tables
db_path = "tradedna_dev.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';").fetchall()
    
    for (tbl,) in tables:
        if tbl not in ("users", "tenants"):
            cursor.execute(f"DELETE FROM {tbl};")
            print(f"Cleared table: {tbl}")
            
    conn.commit()
    conn.close()
    print("Database purged cleanly. User accounts preserved.")

# 2. Clean MT5 Files
mt5_files_dir = r"C:\Users\vaibh\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files"
if os.path.exists(mt5_files_dir):
    for f in glob.glob(os.path.join(mt5_files_dir, "tradedna_*")):
        try:
            os.remove(f)
            print(f"Removed MT5 cache file: {f}")
        except Exception as e:
            print(f"Error removing {f}: {e}")

print("All systems reset to pristine clean state.")
