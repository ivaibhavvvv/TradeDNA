//+------------------------------------------------------------------+
//|                                              TradeDNA_Types.mqh  |
//|                                  Copyright 2026, TradeDNA Team   |
//|                        Exness MT5 Read-Only Intelligence Platform|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradeDNA Team"
#property link      "https://tradedna.io"
#property strict

//+------------------------------------------------------------------+
//| Connector State Machine Enumeration                              |
//+------------------------------------------------------------------+
enum ENUM_CONNECTOR_STATE
{
   STATE_UNPAIRED,
   STATE_PAIRING,
   STATE_CONNECTED,
   STATE_SYNCING,
   STATE_DEGRADED,
   STATE_STORAGE_PRESSURE,
   STATE_BLOCKED_IDENTITY_MISMATCH,
   STATE_REVOKED
};

//+------------------------------------------------------------------+
//| 5-Tuple Broker Identity Structure                                |
//+------------------------------------------------------------------+
struct BrokerIdentity
{
   string   broker;           // "EXNESS"
   long     account_number;   // Account Login
   string   server_name;      // Exness MT5 Server Name
   string   trade_mode;       // "REAL" or "DEMO"
   string   currency;         // Account Currency (e.g. "USD")
};

//+------------------------------------------------------------------+
//| Compound Synchronization Cursor Structure                        |
//+------------------------------------------------------------------+
struct SyncCursor
{
   long     last_sync_time_msc;     // Last Synced Millisecond Timestamp
   ulong    last_sync_deal_ticket;  // Last Synced Deal Ticket
};

//+------------------------------------------------------------------+
//| In-Memory & Spool Event Item Structure                           |
//+------------------------------------------------------------------+
struct EventItem
{
   string   payload_type;     // "DEAL_EVENT", "ORDER_EVENT", "SNAPSHOT_ACCOUNT", etc.
   long     ticket;           // Deal or Order Ticket
   long     time_msc;         // Millisecond timestamp
   string   json_payload;     // Exact serialized JSON string
   uint     crc32;            // Integrity checksum
};

//+------------------------------------------------------------------+
//| Account Snapshot Struct                                          |
//+------------------------------------------------------------------+
struct AccountSnapshotData
{
   string   currency;
   double   balance;
   double   equity;
   double   margin;
   double   margin_free;
   double   margin_level;
   long     leverage;
   string   trade_mode;
   bool     is_hedging;
   string   snapshot_time;
};

//+------------------------------------------------------------------+
//| Deal Event Data Struct                                           |
//+------------------------------------------------------------------+
struct DealEventData
{
   ulong    deal_ticket;
   ulong    order_ticket;
   ulong    position_ticket;
   string   symbol;
   string   deal_type_str;
   string   deal_entry_str;
   double   volume;
   double   price;
   double   commission;
   double   swap;
   double   fee;
   double   profit;
   string   deal_time_str;
   long     deal_time_msc;
   long     deal_magic;
   string   deal_reason_str;
   string   deal_external_id;
};

//+------------------------------------------------------------------+
//| Order Event Data Struct                                          |
//+------------------------------------------------------------------+
struct OrderEventData
{
   ulong    order_ticket;
   ulong    position_ticket;
   string   symbol;
   string   order_type_str;
   string   order_state_str;
   double   volume_initial;
   double   volume_current;
   double   price_open;
   double   sl;
   double   tp;
   string   setup_time_str;
   long     setup_time_msc;
   string   done_time_str;
   long     done_time_msc;
   long     order_magic;
   string   order_reason_str;
   string   order_external_id;
};
