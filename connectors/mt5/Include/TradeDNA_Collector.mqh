//+------------------------------------------------------------------+
//|                                          TradeDNA_Collector.mqh  |
//|                                  Copyright 2026, TradeDNA Team   |
//|                    Read-Only Data Acquisition & Slicing Engine   |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradeDNA Team"
#property link      "https://tradedna.io"
#property strict

#include "TradeDNA_Types.mqh"

//+------------------------------------------------------------------+
//| Map MT5 Deal Type Enum to Authoritative String                   |
//+------------------------------------------------------------------+
string DealTypeToString(long deal_type)
{
   switch(deal_type)
   {
      case DEAL_TYPE_BUY:                      return "DEAL_TYPE_BUY";
      case DEAL_TYPE_SELL:                     return "DEAL_TYPE_SELL";
      case DEAL_TYPE_BALANCE:                  return "DEAL_TYPE_BALANCE";
      case DEAL_TYPE_CREDIT:                   return "DEAL_TYPE_CREDIT";
      case DEAL_TYPE_CHARGE:                   return "DEAL_TYPE_CHARGE";
      case DEAL_TYPE_CORRECTION:               return "DEAL_TYPE_CORRECTION";
      case DEAL_TYPE_BONUS:                    return "DEAL_TYPE_BONUS";
      case DEAL_TYPE_COMMISSION:               return "DEAL_TYPE_COMMISSION";
      case DEAL_TYPE_COMMISSION_DAILY:         return "DEAL_TYPE_COMMISSION_DAILY";
      case DEAL_TYPE_COMMISSION_MONTHLY:       return "DEAL_TYPE_COMMISSION_MONTHLY";
      case DEAL_TYPE_COMMISSION_AGENT_DAILY:   return "DEAL_TYPE_COMMISSION_AGENT_DAILY";
      case DEAL_TYPE_COMMISSION_AGENT_MONTHLY: return "DEAL_TYPE_COMMISSION_AGENT_MONTHLY";
      case DEAL_TYPE_INTEREST:                 return "DEAL_TYPE_INTEREST";
      case DEAL_TYPE_BUY_CANCELED:             return "DEAL_TYPE_BUY_CANCELED";
      case DEAL_TYPE_SELL_CANCELED:            return "DEAL_TYPE_SELL_CANCELED";
      case DEAL_DIVIDEND:                      return "DEAL_DIVIDEND";
      case DEAL_DIVIDEND_FRANKED:              return "DEAL_DIVIDEND_FRANKED";
      case DEAL_TAX:                           return "DEAL_TAX";
      default:                                 return StringFormat("DEAL_TYPE_OTHER_%d", deal_type);
   }
}

//+------------------------------------------------------------------+
//| Map MT5 Deal Entry Enum to String                                |
//+------------------------------------------------------------------+
string DealEntryToString(long entry)
{
   switch(entry)
   {
      case DEAL_ENTRY_IN:     return "DEAL_ENTRY_IN";
      case DEAL_ENTRY_OUT:    return "DEAL_ENTRY_OUT";
      case DEAL_ENTRY_INOUT:  return "DEAL_ENTRY_INOUT";
      case DEAL_ENTRY_OUT_BY: return "DEAL_ENTRY_OUT_BY";
      default:                return "DEAL_ENTRY_STATE";
   }
}

//+------------------------------------------------------------------+
//| Format UTC ISO-8601 Timestamp String                             |
//+------------------------------------------------------------------+
string FormatISOTimestamp(datetime time_sec)
{
   MqlDateTime dt;
   TimeToStruct(time_sec, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d.000Z", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

//+------------------------------------------------------------------+
//| Collect Current Account Snapshot                                 |
//+------------------------------------------------------------------+
void CollectAccountSnapshot(const string connector_id, AccountSnapshotData &snap, string &json_out)
{
   snap.currency     = AccountInfoString(ACCOUNT_CURRENCY);
   snap.balance      = AccountInfoDouble(ACCOUNT_BALANCE);
   snap.equity       = AccountInfoDouble(ACCOUNT_EQUITY);
   snap.margin       = AccountInfoDouble(ACCOUNT_MARGIN);
   snap.margin_free  = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   snap.margin_level = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   snap.leverage     = AccountInfoInteger(ACCOUNT_LEVERAGE);
   snap.trade_mode   = (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL ? "REAL" : "DEMO");
   snap.is_hedging   = (AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
   snap.snapshot_time = FormatISOTimestamp(TimeCurrent());
   
   long account_num = AccountInfoInteger(ACCOUNT_LOGIN);
   
   json_out = StringFormat(
      "{\"schema_version\":\"1.0.0\",\"connector_id\":\"%s\",\"account_number\":%d,\"currency\":\"%s\","
      "\"balance\":\"%.4f\",\"equity\":\"%.4f\",\"margin\":\"%.4f\",\"margin_free\":\"%.4f\","
      "\"margin_level\":\"%.2f\",\"leverage\":%d,\"trade_mode\":\"%s\",\"is_hedging\":%s,\"snapshot_time\":\"%s\"}",
      connector_id, account_num, snap.currency, snap.balance, snap.equity, snap.margin, snap.margin_free,
      snap.margin_level, snap.leverage, snap.trade_mode, (snap.is_hedging ? "true" : "false"), snap.snapshot_time
   );
}

//+------------------------------------------------------------------+
//| Collect Open Positions Snapshot (Informational Display Only)     |
//+------------------------------------------------------------------+
void CollectPositionsSnapshot(const string connector_id, string &json_out)
{
   long account_num = AccountInfoInteger(ACCOUNT_LOGIN);
   string snap_time = FormatISOTimestamp(TimeCurrent());
   int total = PositionsTotal();
   
   string pos_array = "[";
   for(int i = 0; i < total; i++)
   {
      string symbol = PositionGetSymbol(i);
      if(StringLen(symbol) == 0) continue;
      
      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      long pos_type = PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double price_open = PositionGetDouble(POSITION_PRICE_OPEN);
      double price_curr = PositionGetDouble(POSITION_PRICE_CURRENT);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double profit = PositionGetDouble(POSITION_PROFIT);
      double swap = PositionGetDouble(POSITION_SWAP);
      datetime time_open = (datetime)PositionGetInteger(POSITION_TIME);
      long time_msc = PositionGetInteger(POSITION_TIME_MSC);
      long magic = PositionGetInteger(POSITION_MAGIC);
      string comment = PositionGetString(POSITION_COMMENT);
      
      string type_str = (pos_type == POSITION_TYPE_BUY ? "POSITION_TYPE_BUY" : "POSITION_TYPE_SELL");
      
      string item = StringFormat(
         "{\"position_ticket\":%I64u,\"symbol\":\"%s\",\"position_type\":\"%s\",\"volume\":\"%.4f\","
         "\"price_open\":\"%.6f\",\"price_current\":\"%.6f\",\"sl\":\"%.6f\",\"tp\":\"%.6f\","
         "\"profit\":\"%.4f\",\"swap\":\"%.4f\",\"open_time\":\"%s\",\"open_time_msc\":%d,\"magic\":%d,\"comment\":\"%s\"}",
         ticket, symbol, type_str, volume, price_open, price_curr, sl, tp, profit, swap,
         FormatISOTimestamp(time_open), time_msc, magic, comment
      );
      
      if(i > 0) pos_array += ",";
      pos_array += item;
   }
   pos_array += "]";
   
   json_out = StringFormat(
      "{\"schema_version\":\"1.0.0\",\"connector_id\":\"%s\",\"account_number\":%d,\"positions\":%s,\"snapshot_time\":\"%s\"}",
      connector_id, account_num, pos_array, snap_time
   );
}

//+------------------------------------------------------------------+
//| Extract Deal Struct from Active Historical Selection             |
//+------------------------------------------------------------------+
bool ExtractDealEvent(ulong ticket, const string connector_id, DealEventData &deal, string &json_out)
{
   if(!HistoryDealSelect(ticket)) return false;
   
   deal.deal_ticket      = ticket;
   deal.order_ticket     = (ulong)HistoryDealGetInteger(ticket, DEAL_ORDER);
   deal.position_ticket  = (ulong)HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
   deal.symbol           = HistoryDealGetString(ticket, DEAL_SYMBOL);
   deal.deal_type_str    = DealTypeToString(HistoryDealGetInteger(ticket, DEAL_TYPE));
   deal.deal_entry_str   = DealEntryToString(HistoryDealGetInteger(ticket, DEAL_ENTRY));
   deal.volume           = HistoryDealGetDouble(ticket, DEAL_VOLUME);
   deal.price            = HistoryDealGetDouble(ticket, DEAL_PRICE);
   deal.commission       = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
   deal.swap             = HistoryDealGetDouble(ticket, DEAL_SWAP);
   deal.fee              = HistoryDealGetDouble(ticket, DEAL_FEE);
   deal.profit           = HistoryDealGetDouble(ticket, DEAL_PROFIT);
   datetime time_sec     = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
   deal.deal_time_str    = FormatISOTimestamp(time_sec);
   deal.deal_time_msc    = HistoryDealGetInteger(ticket, DEAL_TIME_MSC);
   deal.deal_magic       = HistoryDealGetInteger(ticket, DEAL_MAGIC);
   deal.deal_reason_str  = StringFormat("DEAL_REASON_%d", HistoryDealGetInteger(ticket, DEAL_REASON));
   deal.deal_external_id = HistoryDealGetString(ticket, DEAL_EXTERNAL_ID);
   
   long account_num = AccountInfoInteger(ACCOUNT_LOGIN);
   string event_id = StringFormat("deal_%I64u_%d", ticket, deal.deal_time_msc);
   string obs_id = StringFormat("obs_%I64u_%d", ticket, GetTickCount());
   
   json_out = StringFormat(
      "{\"schema_version\":\"1.0.0\",\"observation_id\":\"%s\",\"event_id\":\"%s\",\"connector_id\":\"%s\","
      "\"account_number\":%d,\"deal_ticket\":%I64u,\"order_ticket\":%I64u,\"position_ticket\":%I64u,\"symbol\":\"%s\","
      "\"deal_type\":\"%s\",\"deal_entry\":\"%s\",\"volume\":\"%.4f\",\"price\":\"%.6f\",\"commission\":\"%.4f\","
      "\"swap\":\"%.4f\",\"fee\":\"%.4f\",\"profit\":\"%.4f\",\"deal_time\":\"%s\",\"deal_time_msc\":%d,"
      "\"deal_magic\":%d,\"deal_reason\":\"%s\",\"deal_external_id\":\"%s\",\"source_type\":\"EVENT_STREAM\"}",
      obs_id, event_id, connector_id, account_num, deal.deal_ticket, deal.order_ticket, deal.position_ticket,
      deal.symbol, deal.deal_type_str, deal.deal_entry_str, deal.volume, deal.price, deal.commission,
      deal.swap, deal.fee, deal.profit, deal.deal_time_str, deal.deal_time_msc, deal.deal_magic,
      deal.deal_reason_str, deal.deal_external_id
   );
   return true;
}

//+------------------------------------------------------------------+
//| Deterministic Deal Sorter: (DEAL_TIME_MSC ASC, DEAL_TICKET ASC)  |
//+------------------------------------------------------------------+
void SortDeals(DealEventData &deals[])
{
   int size = ArraySize(deals);
   for(int i = 0; i < size - 1; i++)
   {
      for(int j = 0; j < size - i - 1; j++)
      {
         bool swap_needed = false;
         if(deals[j].deal_time_msc > deals[j + 1].deal_time_msc)
         {
            swap_needed = true;
         }
         else if(deals[j].deal_time_msc == deals[j + 1].deal_time_msc && deals[j].deal_ticket > deals[j + 1].deal_ticket)
         {
            swap_needed = true;
         }
         
         if(swap_needed)
         {
            DealEventData temp = deals[j];
            deals[j] = deals[j + 1];
            deals[j + 1] = temp;
         }
      }
   }
}
