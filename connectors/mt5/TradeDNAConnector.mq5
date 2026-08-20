//+------------------------------------------------------------------+
//|                                           TradeDNAConnector.mq5  |
//|                                  Copyright 2026, TradeDNA Team   |
//|                        Exness MT5 Read-Only Intelligence Platform|
//+------------------------------------------------------------------+
#property copyright   "Copyright 2026, TradeDNA Team"
#property link        "https://tradedna.io"
#property version     "1.00"
#property description "TradeDNA Exness MT5 Read-Only Intelligence & Analytics Connector"
#property strict

// ===================================================================
// ABSOLUTE PROHIBITION CHECK:
// This Expert Advisor is STRICTLY READ-ONLY.
// Zero trade execution capabilities (OrderSend, OrderModify, etc.) exist.
// ===================================================================

#include "Include\TradeDNA_Types.mqh"
#include "Include\TradeDNA_Crypto.mqh"
#include "Include\TradeDNA_Vault.mqh"
#include "Include\TradeDNA_Buffer.mqh"
#include "Include\TradeDNA_Collector.mqh"
#include "Include\TradeDNA_Network.mqh"

//+------------------------------------------------------------------+
//| EA Input Parameters (Pairing Token is single-use, never secret)  |
//+------------------------------------------------------------------+
input string   InpTradeDNABaseUrl   = "http://127.0.0.1:8000"; // TradeDNA API Base URL
input string   InpPairingToken      = "";                       // 64-Char Pairing Token (From Dashboard)
input bool     InpForceRePair       = false;                    // Force Re-Pairing with New Token
input int      InpHeartbeatInterval = 30;                       // Heartbeat Interval (Seconds)
input int      InpSyncWindowDays    = 30;                       // Initial Historical Sync Step (Days)

//+------------------------------------------------------------------+
//| Global Connector Runtime State                                   |
//+------------------------------------------------------------------+
ENUM_CONNECTOR_STATE g_state = STATE_UNPAIRED;
BrokerIdentity       g_current_identity;
SyncCursor           g_cursor;
string               g_device_id = "";
string               g_device_secret = "";

datetime             g_last_heartbeat_time = 0;
datetime             g_last_snapshot_time = 0;
datetime             g_last_incremental_time = 0;
int                  g_backoff_seconds = 0;
datetime             g_next_retry_time = 0;
bool                 g_initial_sync_complete = false;

//+------------------------------------------------------------------+
//| Update Chart Visual Dashboard Overlay                            |
//+------------------------------------------------------------------+
void UpdateChartStatus()
{
   string state_str = "UNKNOWN";
   switch(g_state)
   {
      case STATE_UNPAIRED:                 state_str = "UNPAIRED (Please input pairing token)"; break;
      case STATE_PAIRING:                  state_str = "PAIRING IN PROGRESS..."; break;
      case STATE_CONNECTED:                state_str = "CONNECTED & OBSERVING"; break;
      case STATE_SYNCING:                  state_str = "SYNCING HISTORICAL DEALS"; break;
      case STATE_DEGRADED:                 state_str = "DEGRADED (Retrying connection)"; break;
      case STATE_STORAGE_PRESSURE:         state_str = "DEGRADED (STORAGE PRESSURE - SPOOL FULL)"; break;
      case STATE_BLOCKED_IDENTITY_MISMATCH:state_str = "BLOCKED (Account Identity Mismatch)"; break;
      case STATE_REVOKED:                  state_str = "REVOKED (Device deactivated on server)"; break;
   }
   
   string comment = StringFormat(
      "====================================================\n"
      " TradeDNA Exness MT5 Read-Only Connector v1.00\n"
      " Mode: STRICTLY READ-ONLY (Zero Execution Proved)\n"
      " Status: %s\n"
      " Account: %I64d (%s) | Server: %s\n"
      " Device ID: %s\n"
      " Last Sync Time (MSC): %I64d\n"
      " Buffered Events: %d | Storage Pressure: %s\n"
      "====================================================",
      state_str, g_current_identity.account_number, g_current_identity.currency,
      g_current_identity.server_name, (StringLen(g_device_id) > 0 ? g_device_id : "N/A"),
      g_cursor.last_sync_time_msc, g_buffer_count, (g_storage_pressure ? "YES" : "NO")
   );
   Comment(comment);
}

//+------------------------------------------------------------------+
//| Verify 5-Tuple Broker Identity                                   |
//+------------------------------------------------------------------+
bool PopulateCurrentBrokerIdentity()
{
   g_current_identity.broker         = "EXNESS";
   g_current_identity.account_number = AccountInfoInteger(ACCOUNT_LOGIN);
   g_current_identity.server_name    = AccountInfoString(ACCOUNT_SERVER);
   g_current_identity.trade_mode     = (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "REAL" : "DEMO");
   g_current_identity.currency       = AccountInfoString(ACCOUNT_CURRENCY);
   
   if(g_current_identity.account_number <= 0 || StringLen(g_current_identity.server_name) == 0)
   {
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[TradeDNA Connector] Initializing Exness MT5 Read-Only Connector...");
   
   if(!PopulateCurrentBrokerIdentity())
   {
      Print("[TradeDNA Connector] Error: Unable to read account information from terminal.");
      return INIT_FAILED;
   }
   
   PrintFormat("[TradeDNA Connector] Active Terminal Account: #%I64d (%s) on Server: %s", 
               g_current_identity.account_number, g_current_identity.currency, g_current_identity.server_name);
   
   // 1. Check if this specific account is ALREADY paired in its local vault
   string saved_device_id = "";
   string saved_device_secret = "";
   BrokerIdentity stored_identity;
   SyncCursor stored_cursor;
   
   bool has_vault = LoadVaultCredentials(g_current_identity.account_number, saved_device_id, saved_device_secret);
   bool has_state = LoadOperationalState(g_current_identity.account_number, stored_identity, stored_cursor);
   
   if(!InpForceRePair && has_vault && StringLen(saved_device_id) > 0 && StringLen(saved_device_secret) > 0)
   {
      // Already Paired! Connect immediately using this account's dedicated vault.
      g_device_id = saved_device_id;
      g_device_secret = saved_device_secret;
      
      if(has_state && stored_identity.account_number == g_current_identity.account_number)
      {
         g_cursor = stored_cursor;
      }
      else
      {
         g_cursor.last_sync_time_msc = 0;
         g_cursor.last_sync_deal_ticket = 0;
         SaveOperationalState(g_current_identity, g_cursor);
      }
      
      g_state = STATE_CONNECTED;
      PrintFormat("[TradeDNA Connector] SUCCESS: Account #%I64d is paired and active (Device ID: %s)", 
                  g_current_identity.account_number, g_device_id);
      EventSetTimer(1);
      UpdateChartStatus();
      return INIT_SUCCEEDED;
   }
   
   // 2. If NOT yet paired in vault, check if user provided a valid new pairing token
   if(StringLen(InpPairingToken) >= 32)
   {
      g_state = STATE_PAIRING;
      UpdateChartStatus();
      
      string new_device_id = "";
      string new_device_secret = "";
      
      if(PerformHandshakeExchange(InpTradeDNABaseUrl, InpPairingToken, g_current_identity, new_device_id, new_device_secret))
      {
         g_device_id = new_device_id;
         g_device_secret = new_device_secret;
         g_cursor.last_sync_time_msc = 0;
         g_cursor.last_sync_deal_ticket = 0;
         
         SaveVaultCredentials(g_current_identity.account_number, g_device_id, g_device_secret);
         SaveOperationalState(g_current_identity, g_cursor);
         
         g_state = STATE_CONNECTED;
         PrintFormat("[TradeDNA Connector] SUCCESS: Account #%I64d successfully paired with Device ID: %s", 
                     g_current_identity.account_number, g_device_id);
         EventSetTimer(1);
         UpdateChartStatus();
         return INIT_SUCCEEDED;
      }
      else
      {
         PrintFormat("[TradeDNA Connector] Handshake failed with provided token for Account #%I64d.", 
                     g_current_identity.account_number);
      }
   }
   
   // 3. Unpaired state
   g_device_id = "";
   g_device_secret = "";
   g_state = STATE_UNPAIRED;
   PrintFormat("[TradeDNA Connector] Account #%I64d is UNPAIRED. Please enter a fresh pairing token in EA Inputs (F7).", 
               g_current_identity.account_number);
   
   EventSetTimer(1); // 1-Second Timer Tick
   UpdateChartStatus();
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   Print("[TradeDNA Connector] Deinitialized. Reason code: ", reason);
}

//+------------------------------------------------------------------+
//| Real-Time Trade Transaction Hook (<1ms Execution Guaranteed)     |
//+------------------------------------------------------------------+
void OnTradeTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
{
   // Strictly Lightweight: Extract metadata, push to ring buffer, return immediately!
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      ulong deal_ticket = trans.deal;
      if(deal_ticket > 0)
      {
         DealEventData deal;
         string json_payload;
         if(ExtractDealEvent(deal_ticket, g_device_id, deal, json_payload))
         {
            PushEvent("DEAL_EVENT", (long)deal.deal_ticket, deal.deal_time_msc, json_payload);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Asynchronous Timer Tick Handler (1000ms Interval)                |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(g_state == STATE_UNPAIRED || g_state == STATE_BLOCKED_IDENTITY_MISMATCH || g_state == STATE_REVOKED)
   {
      UpdateChartStatus();
      return;
   }
   
   datetime now_sec = TimeCurrent();
   
   // Check backoff timeout
   if(now_sec < g_next_retry_time)
   {
      UpdateChartStatus();
      return;
   }
   
   // 1. Drain Disk Spool First (FIFO Priority)
   if(HasDiskSpoolRecords())
   {
      EventItem spool_batch[];
      int count = DrainSpoolBatch(spool_batch, 20);
      for(int i = 0; i < count; i++)
      {
         long ack_time = 0;
         long ack_ticket = 0;
         int code = SendSignedSyncEnvelope(
            InpTradeDNABaseUrl, g_device_id, g_device_secret,
            spool_batch[i].payload_type, spool_batch[i].json_payload,
            ack_time, ack_ticket
         );
         
         if(code == 200 || code == 202)
         {
            if(ack_time > g_cursor.last_sync_time_msc ||
              (ack_time == g_cursor.last_sync_time_msc && (ulong)ack_ticket > g_cursor.last_sync_deal_ticket))
            {
               g_cursor.last_sync_time_msc = ack_time;
               g_cursor.last_sync_deal_ticket = (ulong)ack_ticket;
               SaveOperationalState(g_current_identity, g_cursor);
            }
            g_backoff_seconds = 0;
            g_state = STATE_CONNECTED;
         }
         else
         {
            HandleNetworkError(code);
            UpdateChartStatus();
            return;
         }
      }
   }
   
   // 2. Drain In-Memory Ring Buffer Events
   while(g_buffer_count > 0)
   {
      EventItem item;
      if(PopEvent(item))
      {
         long ack_time = 0;
         long ack_ticket = 0;
         int code = SendSignedSyncEnvelope(
            InpTradeDNABaseUrl, g_device_id, g_device_secret,
            item.payload_type, item.json_payload,
            ack_time, ack_ticket
         );
         
         if(code == 200 || code == 202)
         {
            if(ack_time > g_cursor.last_sync_time_msc ||
              (ack_time == g_cursor.last_sync_time_msc && (ulong)ack_ticket > g_cursor.last_sync_deal_ticket))
            {
               g_cursor.last_sync_time_msc = ack_time;
               g_cursor.last_sync_deal_ticket = (ulong)ack_ticket;
               SaveOperationalState(g_current_identity, g_cursor);
            }
            g_backoff_seconds = 0;
            g_state = STATE_CONNECTED;
         }
         else
         {
            // Push back or spool to disk on error
            SpoolEventToDisk(item);
            HandleNetworkError(code);
            UpdateChartStatus();
            return;
         }
      }
   }
   
   // 3. Heartbeat Transmission (Every 30s)
   if(now_sec - g_last_heartbeat_time >= InpHeartbeatInterval)
   {
      g_last_heartbeat_time = now_sec;
      string hb_json = StringFormat(
         "{\"schema_version\":\"1.0.0\",\"connector_id\":\"%s\",\"account_number\":%d,\"server_name\":\"%s\","
         "\"terminal_build\":%d,\"connector_version\":\"1.0.0\",\"timestamp\":\"%s\",\"ping_latency_ms\":0.0}",
         g_device_id, g_current_identity.account_number, g_current_identity.server_name,
         (int)TerminalInfoInteger(TERMINAL_BUILD), FormatISOTimestamp(now_sec)
      );
      
      long dummy_t = 0, dummy_k = 0;
      SendSignedSyncEnvelope(InpTradeDNABaseUrl, g_device_id, g_device_secret, "HEARTBEAT", hb_json, dummy_t, dummy_k);
   }
   
   // 4. Account & Position Snapshots (Every 30s)
   if(now_sec - g_last_snapshot_time >= 30)
   {
      g_last_snapshot_time = now_sec;
      AccountSnapshotData snap;
      string snap_json;
      CollectAccountSnapshot(g_device_id, snap, snap_json);
      
      long dummy_t = 0, dummy_k = 0;
      SendSignedSyncEnvelope(InpTradeDNABaseUrl, g_device_id, g_device_secret, "SNAPSHOT_ACCOUNT", snap_json, dummy_t, dummy_k);
      
      string pos_json;
      CollectPositionsSnapshot(g_device_id, pos_json);
      SendSignedSyncEnvelope(InpTradeDNABaseUrl, g_device_id, g_device_secret, "SNAPSHOT_POSITIONS", pos_json, dummy_t, dummy_k);
   }
   
   // 5. Adaptive Incremental Sync (Every 30s Overlapping 24h Window)
   if(now_sec - g_last_incremental_time >= 30)
   {
      g_last_incremental_time = now_sec;
      PerformAdaptiveIncrementalSync();
   }
   
   UpdateChartStatus();
}

//+------------------------------------------------------------------+
//| Adaptive Incremental Synchronization with Overlapping Window     |
//+------------------------------------------------------------------+
void PerformAdaptiveIncrementalSync()
{
   datetime to_date = TimeCurrent();
   datetime from_date = to_date - (86400 * 2); // 48-Hour Overlapping Window
   
   if(!HistorySelect(from_date, to_date)) return;
   
   int total_deals = HistoryDealsTotal();
   for(int i = 0; i < total_deals; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket <= 0) continue;
      
      long time_msc = HistoryDealGetInteger(ticket, DEAL_TIME_MSC);
      
      // Check if strictly newer than cursor
      if(time_msc > g_cursor.last_sync_time_msc ||
        (time_msc == g_cursor.last_sync_time_msc && ticket > g_cursor.last_sync_deal_ticket))
      {
         DealEventData deal;
         string json_payload;
         if(ExtractDealEvent(ticket, g_device_id, deal, json_payload))
         {
            PushEvent("DEAL_EVENT", (long)deal.deal_ticket, deal.deal_time_msc, json_payload);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Handle Network / HTTP Errors with Exponential Backoff            |
//+------------------------------------------------------------------+
void HandleNetworkError(int http_code)
{
   if(http_code == 401)
   {
      Print("[TradeDNA Connector] Device credentials revoked or unauthenticated on server. Vault purged.");
      PurgeVault(g_current_identity.account_number);
      g_device_id = "";
      g_device_secret = "";
      g_state = STATE_REVOKED;
      UpdateChartStatus();
      return;
   }
   
   g_state = STATE_DEGRADED;
   if(g_backoff_seconds == 0) g_backoff_seconds = 5;
   else g_backoff_seconds = MathMin(g_backoff_seconds * 2, 60);
   
   g_next_retry_time = TimeCurrent() + g_backoff_seconds;
   PrintFormat("[TradeDNA Connector] Network error (HTTP %d). Backing off for %d seconds.", http_code, g_backoff_seconds);
}
