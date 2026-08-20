//+------------------------------------------------------------------+
//|                                              TradeDNA_Vault.mqh  |
//|                                  Copyright 2026, TradeDNA Team   |
//|                    Encrypted Credential Vault & State Storage    |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradeDNA Team"
#property link      "https://tradedna.io"
#property strict

#include "TradeDNA_Types.mqh"
#include "TradeDNA_Crypto.mqh"

#define LEGACY_VAULT_FILE  "tradedna_vault.dat"
#define LEGACY_STATE_FILE  "tradedna_state.bin"

//+------------------------------------------------------------------+
//| Per-Account Isolated Storage File Name Helpers                   |
//+------------------------------------------------------------------+
string GetVaultFileName(const long account_number)
{
   if(account_number > 0)
      return StringFormat("tradedna_vault_%d.dat", account_number);
   return LEGACY_VAULT_FILE;
}

string GetStateFileName(const long account_number)
{
   if(account_number > 0)
      return StringFormat("tradedna_state_%d.bin", account_number);
   return LEGACY_STATE_FILE;
}

//+------------------------------------------------------------------+
//| Save Credential Vault with Authenticated Encryption              |
//+------------------------------------------------------------------+
bool SaveVaultCredentials(const long account_number, const string device_id, const string device_secret_hex)
{
   string filename = GetVaultFileName(account_number);
   int handle = FileOpen(filename, FILE_WRITE | FILE_BIN);
   if(handle == INVALID_HANDLE)
   {
      Print("[TradeDNA Vault] Error: Unable to open vault file for writing: ", filename, " Error code: ", GetLastError());
      return false;
   }
   
   // 1. Generate random 256-bit DEK & random 128-bit IV
   uchar dek[32];
   uchar iv[16];
   for(int i = 0; i < 32; i++) dek[i] = (uchar)(MathRand() ^ (GetTickCount() & 0xFF));
   for(int i = 0; i < 16; i++) iv[i] = (uchar)(MathRand() ^ ((GetTickCount() >> 4) & 0xFF));
   
   // 2. Encrypt device_secret using DEK
   uchar secret_bytes[];
   HexToBytes(device_secret_hex, secret_bytes);
   uchar cipher_bytes[];
   ArrayResize(cipher_bytes, ArraySize(secret_bytes));
   for(int i = 0; i < ArraySize(secret_bytes); i++)
   {
      cipher_bytes[i] = (uchar)(secret_bytes[i] ^ dek[i % 32] ^ iv[i % 16]);
   }
   
   // 3. Compute Integrity MAC: HMAC-SHA256(DEK, cipher_bytes)
   string dek_hex = BytesToHex(dek);
   string mac_hex = ComputeHMACSHA256(dek_hex, BytesToHex(cipher_bytes));
   
   // 4. Write binary container format
   FileWriteString(handle, device_id);
   FileWriteInteger(handle, ArraySize(cipher_bytes));
   FileWriteArray(handle, cipher_bytes);
   FileWriteArray(handle, iv);
   FileWriteArray(handle, dek);
   FileWriteString(handle, mac_hex);
   
   FileClose(handle);
   return true;
}

//+------------------------------------------------------------------+
//| Load Credential Vault and Verify Integrity                       |
//+------------------------------------------------------------------+
bool LoadVaultCredentials(const long account_number, string &device_id, string &device_secret_hex)
{
   string filename = GetVaultFileName(account_number);
   if(!FileIsExist(filename))
   {
      // Fallback to legacy single-account vault file if present
      if(FileIsExist(LEGACY_VAULT_FILE))
         filename = LEGACY_VAULT_FILE;
      else
         return false;
   }
   
   int handle = FileOpen(filename, FILE_READ | FILE_BIN);
   if(handle == INVALID_HANDLE)
   {
      return false;
   }
   
   device_id = FileReadString(handle);
   int cipher_len = (int)FileReadInteger(handle);
   if(cipher_len <= 0 || cipher_len > 1024)
   {
      FileClose(handle);
      return false;
   }
   
   uchar cipher_bytes[];
   ArrayResize(cipher_bytes, cipher_len);
   FileReadArray(handle, cipher_bytes);
   
   uchar iv[16];
   FileReadArray(handle, iv);
   
   uchar dek[32];
   FileReadArray(handle, dek);
   
   string expected_mac = FileReadString(handle);
   FileClose(handle);
   
   // Verify Authenticated MAC
   string dek_hex = BytesToHex(dek);
   string computed_mac = ComputeHMACSHA256(dek_hex, BytesToHex(cipher_bytes));
   if(StringCompare(computed_mac, expected_mac, false) != 0)
   {
      Print("[TradeDNA Vault] CRITICAL: Vault integrity verification failed for ", filename);
      return false;
   }
   
   // Decrypt device_secret
   uchar secret_bytes[];
   ArrayResize(secret_bytes, cipher_len);
   for(int i = 0; i < cipher_len; i++)
   {
      secret_bytes[i] = (uchar)(cipher_bytes[i] ^ dek[i % 32] ^ iv[i % 16]);
   }
   
   device_secret_hex = BytesToHex(secret_bytes);
   return true;
}

//+------------------------------------------------------------------+
//| Purge Vault Credentials upon Revocation                          |
//+------------------------------------------------------------------+
void PurgeVault(const long account_number = 0)
{
   string v_file = GetVaultFileName(account_number);
   string s_file = GetStateFileName(account_number);
   if(FileIsExist(v_file)) FileDelete(v_file);
   if(FileIsExist(s_file)) FileDelete(s_file);
   if(account_number == 0)
   {
      if(FileIsExist(LEGACY_VAULT_FILE)) FileDelete(LEGACY_VAULT_FILE);
      if(FileIsExist(LEGACY_STATE_FILE)) FileDelete(LEGACY_STATE_FILE);
   }
}

//+------------------------------------------------------------------+
//| Save Operational Sync State & Broker Identity                    |
//+------------------------------------------------------------------+
bool SaveOperationalState(const BrokerIdentity &identity, const SyncCursor &cursor)
{
   string filename = GetStateFileName(identity.account_number);
   int handle = FileOpen(filename, FILE_WRITE | FILE_BIN);
   if(handle == INVALID_HANDLE) return false;
   
   FileWriteString(handle, identity.broker);
   FileWriteLong(handle, identity.account_number);
   FileWriteString(handle, identity.server_name);
   FileWriteString(handle, identity.trade_mode);
   FileWriteString(handle, identity.currency);
   
   FileWriteLong(handle, cursor.last_sync_time_msc);
   FileWriteLong(handle, (long)cursor.last_sync_deal_ticket);
   
   FileClose(handle);
   return true;
}

//+------------------------------------------------------------------+
//| Load Operational Sync State                                      |
//+------------------------------------------------------------------+
bool LoadOperationalState(const long account_number, BrokerIdentity &identity, SyncCursor &cursor)
{
   string filename = GetStateFileName(account_number);
   if(!FileIsExist(filename))
   {
      if(FileIsExist(LEGACY_STATE_FILE))
         filename = LEGACY_STATE_FILE;
      else
         return false;
   }
   
   int handle = FileOpen(filename, FILE_READ | FILE_BIN);
   if(handle == INVALID_HANDLE) return false;
   
   identity.broker = FileReadString(handle);
   identity.account_number = FileReadLong(handle);
   identity.server_name = FileReadString(handle);
   identity.trade_mode = FileReadString(handle);
   identity.currency = FileReadString(handle);
   
   cursor.last_sync_time_msc = FileReadLong(handle);
   cursor.last_sync_deal_ticket = (ulong)FileReadLong(handle);
   
   FileClose(handle);
   return true;
}
