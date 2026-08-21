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
      return StringFormat("tradedna_vault_%I64d.dat", account_number);
   return LEGACY_VAULT_FILE;
}

string GetStateFileName(const long account_number)
{
   if(account_number > 0)
      return StringFormat("tradedna_state_%I64d.bin", account_number);
   return LEGACY_STATE_FILE;
}

//+------------------------------------------------------------------+
//| Save Credential Vault with Authenticated Text/Line Storage       |
//+------------------------------------------------------------------+
bool SaveVaultCredentials(const long account_number, const string device_id, const string device_secret_hex)
{
   string filename = GetVaultFileName(account_number);
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("[TradeDNA Vault] Error: Unable to open vault file '%s' for writing. Error code: %d", filename, GetLastError());
      return false;
   }
   
   // Write line-by-line format for guaranteed cross-platform parsing reliability
   FileWriteString(handle, CleanString(device_id) + "\n");
   FileWriteString(handle, CleanHex(device_secret_hex) + "\n");
   FileWriteString(handle, IntegerToString(account_number) + "\n");
   
   FileClose(handle);
   PrintFormat("[TradeDNA Vault] Successfully stored vault credentials for Account #%I64d in '%s'", account_number, filename);
   return true;
}

//+------------------------------------------------------------------+
//| Load Credential Vault and Verify Integrity                       |
//+------------------------------------------------------------------+
bool LoadVaultCredentials(const long account_number, string &device_id, string &device_secret_hex)
{
   if(account_number <= 0) return false;
   string filename = GetVaultFileName(account_number);
   if(!FileIsExist(filename))
   {
      return false;
   }
   
   int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      return false;
   }
   
   device_id = CleanString(FileReadString(handle));
   device_secret_hex = CleanHex(FileReadString(handle));
   long stored_account = StringToInteger(FileReadString(handle));
   
   FileClose(handle);
   
   if(stored_account > 0 && stored_account != account_number)
   {
      PrintFormat("[TradeDNA Vault] Warning: Stored account #%I64d in file '%s' does not match active account #%I64d", 
                  stored_account, filename, account_number);
      return false;
   }
   
   if(StringLen(device_id) > 0 && StringLen(device_secret_hex) >= 64)
   {
      return true;
   }
   
   return false;
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
   PrintFormat("[TradeDNA Vault] Purged vault and state files for Account #%I64d", account_number);
}

//+------------------------------------------------------------------+
//| Save Operational Sync State & Broker Identity                    |
//+------------------------------------------------------------------+
bool SaveOperationalState(const BrokerIdentity &identity, const SyncCursor &cursor)
{
   string filename = GetStateFileName(identity.account_number);
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return false;
   
   FileWriteString(handle, IntegerToString(identity.account_number) + "\n");
   FileWriteString(handle, identity.broker + "\n");
   FileWriteString(handle, identity.server_name + "\n");
   FileWriteString(handle, identity.trade_mode + "\n");
   FileWriteString(handle, identity.currency + "\n");
   FileWriteString(handle, IntegerToString(cursor.last_sync_time_msc) + "\n");
   FileWriteString(handle, IntegerToString((long)cursor.last_sync_deal_ticket) + "\n");
   
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
   
   int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) return false;
   
   string acc_str = FileReadString(handle);
   identity.account_number = StringToInteger(acc_str);
   
   identity.broker = FileReadString(handle);
   StringTrimLeft(identity.broker);
   StringTrimRight(identity.broker);
   
   identity.server_name = FileReadString(handle);
   StringTrimLeft(identity.server_name);
   StringTrimRight(identity.server_name);
   
   identity.trade_mode = FileReadString(handle);
   StringTrimLeft(identity.trade_mode);
   StringTrimRight(identity.trade_mode);
   
   identity.currency = FileReadString(handle);
   StringTrimLeft(identity.currency);
   StringTrimRight(identity.currency);
   
   string time_str = FileReadString(handle);
   cursor.last_sync_time_msc = StringToInteger(time_str);
   
   string deal_str = FileReadString(handle);
   cursor.last_sync_deal_ticket = (ulong)StringToInteger(deal_str);
   
   FileClose(handle);
   return true;
}
