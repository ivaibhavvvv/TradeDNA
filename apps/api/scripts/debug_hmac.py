import sqlite3
import hmac
import hashlib

conn = sqlite3.connect('tradedna_dev.db')
rows = conn.execute('SELECT id, hex(id), device_secret, device_secret_hash FROM devices').fetchall()
for r in rows:
    print('Row:', r[0], r[1], r[2])

canonical = "7c5bcafc-5509-4545-99bb-439762b917c9|1787225658593|0074fb53e944ab56876831a163e1184e|1b1e68d70571d128abae07a5b6fd564cd9aa83b25f70336fa2f703ce7ac73832"
# Let's test with the device_secret of that device
for r in rows:
    secret = r[2]
    sig_hex = hmac.new(bytes.fromhex(secret), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
    sig_raw = hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
    print('Device', r[0], 'sig_hex:', sig_hex, 'sig_raw:', sig_raw)
