import sqlite3
import hmac
import hashlib

conn = sqlite3.connect('tradedna_dev.db')
row = conn.execute("SELECT id, hex(id), device_secret FROM devices WHERE hex(id) LIKE '%976BA833%' OR id LIKE '%976ba833%'").fetchone()
if not row:
    row = conn.execute("SELECT id, hex(id), device_secret FROM devices").fetchone()

print("Found DB device:", row)
secret = row[2]
canonical = "976ba833-10cf-4916-9adb-7f7b30d286ec|1787229232671|26fab27df2f8356f6744228fb5b849c0|f15acef08e50d5e953dff5450c8bc8229cc8e4952cd2527a27d2b8c36e18d47c"

sig_hex = hmac.new(bytes.fromhex(secret), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
sig_utf8 = hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()

print("Secret:", secret)
print("sig_hex: ", sig_hex)
print("sig_utf8:", sig_utf8)
print("MT5 sent: 1317f322056a695cb45f0b7a17fb63ad05f5f36ede0f12b2ca3a8f1c41cb7a23")
