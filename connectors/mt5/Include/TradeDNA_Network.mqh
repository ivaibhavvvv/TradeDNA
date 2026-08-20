//+------------------------------------------------------------------+
//|                                             TradeDNA_Network.mqh |
//|                                  Copyright 2026, TradeDNA Team   |
//|               HTTPS WebRequest Transport & Canonical Signing     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradeDNA Team"
#property link      "https://tradedna.io"
#property strict

#include "TradeDNA_Types.mqh"
#include "TradeDNA_Crypto.mqh"

//+------------------------------------------------------------------+
//| Simple JSON string value extractor                               |
//+------------------------------------------------------------------+
string ExtractJsonString(const string json, const string key)
{
   string search = "\"" + key + "\":\"";
   int pos = StringFind(json, search);
   if(pos < 0) return "";
   
   pos += StringLen(search);
   int end_pos = StringFind(json, "\"", pos);
   if(end_pos < 0) return "";
   
   return StringSubstr(json, pos, end_pos - pos);
}

//+------------------------------------------------------------------+
//| Simple JSON integer value extractor                              |
//+------------------------------------------------------------------+
long ExtractJsonLong(const string json, const string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(json, search);
   if(pos < 0) return 0;
   
   pos += StringLen(search);
   int end_pos = StringFind(json, ",", pos);
   if(end_pos < 0) end_pos = StringFind(json, "}", pos);
   if(end_pos < 0) return 0;
   
   string val_str = StringSubstr(json, pos, end_pos - pos);
   StringTrimLeft(val_str);
   StringTrimRight(val_str);
   return StringToInteger(val_str);
}

//+------------------------------------------------------------------+
//| Perform Handshake Exchange with TradeDNA Backend                 |
//+------------------------------------------------------------------+
bool PerformHandshakeExchange(
   const string base_url,
   const string pairing_token,
   const BrokerIdentity &identity,
   string &device_id_out,
   string &device_secret_out
)
{
   string url = base_url + "/api/v1/exness/connection/exchange";
   string nonce = GenerateNonce(16);
   
   string payload = StringFormat(
      "{\"pairing_token\":\"%s\",\"client_nonce\":\"%s\",\"broker\":\"%s\",\"account_number\":%d,"
      "\"server_name\":\"%s\",\"trade_mode\":\"%s\",\"currency\":\"%s\",\"terminal_build\":%d,\"connector_version\":\"1.0.0\"}",
      pairing_token, nonce, identity.broker, identity.account_number, identity.server_name,
      identity.trade_mode, identity.currency, (int)TerminalInfoInteger(TERMINAL_BUILD)
   );
   
   uchar post_data[];
   StringToCharArray(payload, post_data, 0, StringLen(payload), CP_UTF8);
   
   string headers = "Content-Type: application/json\r\n";
   uchar result_data[];
   string result_headers;
   
   ResetLastError();
   int res = WebRequest("POST", url, headers, 10000, post_data, result_data, result_headers);
   
   if(res == 200)
   {
      string resp_str = CharArrayToString(result_data, 0, WHOLE_ARRAY, CP_UTF8);
      device_id_out = ExtractJsonString(resp_str, "device_id");
      device_secret_out = ExtractJsonString(resp_str, "device_secret");
      
      if(StringLen(device_id_out) > 0 && StringLen(device_secret_out) > 0)
      {
         Print("[TradeDNA Network] Handshake exchange successful. Registered Device ID: ", device_id_out);
         return true;
      }
   }
   else
   {
      int err = GetLastError();
      if(err == 4014 || res == -1)
      {
         Print("=========================================================================");
         Print("[TradeDNA Error] WebRequest is NOT enabled in MetaTrader 5 options!");
         Print("[TradeDNA Fix] In MT5: Click Tools -> Options -> Expert Advisors tab");
         Print("[TradeDNA Fix] 1. Check 'Allow WebRequest for listed URL:'");
         Print("[TradeDNA Fix] 2. Add: http://127.0.0.1:8000");
         Print("[TradeDNA Fix] 3. Click OK, then press F7 on chart to reconnect.");
         Print("=========================================================================");
      }
      else if(res == 401)
      {
         Print("[TradeDNA Error] Pairing token expired or already used (HTTP 401). Please generate a fresh token from TradeDNA Dashboard.");
      }
      else
      {
         string err_body = CharArrayToString(result_data, 0, WHOLE_ARRAY, CP_UTF8);
         PrintFormat("[TradeDNA Network] Handshake failed with HTTP status %d, Error: %d. Response: %s", res, err, err_body);
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Send Signed Data Sync Envelope to TradeDNA Backend               |
//+------------------------------------------------------------------+
int SendSignedSyncEnvelope(
   const string base_url,
   const string device_id,
   const string device_secret_hex,
   const string payload_type,
   const string inner_json_payload,
   long &ack_time_msc,
   long &ack_deal_ticket
)
{
   string url = base_url + "/api/v1/exness/sync";
   string envelope_json = StringFormat("{\"payload_type\":\"%s\",\"data\":%s}", payload_type, inner_json_payload);
   
   long timestamp_ms = (long)TimeGMT() * 1000 + (long)(GetTickCount() % 1000);
   string nonce = GenerateNonce(16);
   
   // Compute RFC 2104 HMAC-SHA256 signature
   string signature = SignRequestPayload(device_id, timestamp_ms, nonce, envelope_json, device_secret_hex);
   
   string headers = "Content-Type: application/json\r\n" +
                    "X-TradeDNA-Device-ID: " + device_id + "\r\n" +
                    "X-TradeDNA-Timestamp: " + IntegerToString(timestamp_ms) + "\r\n" +
                    "X-TradeDNA-Nonce: " + nonce + "\r\n" +
                    "X-TradeDNA-Signature: " + signature + "\r\n";
                    
   uchar post_data[];
   StringToCharArray(envelope_json, post_data, 0, StringLen(envelope_json), CP_UTF8);
   
   uchar result_data[];
   string result_headers;
   
   ResetLastError();
   int http_code = WebRequest("POST", url, headers, 10000, post_data, result_data, result_headers);
   
   if(http_code == 200 || http_code == 202)
   {
      string resp_str = CharArrayToString(result_data, 0, WHOLE_ARRAY, CP_UTF8);
      ack_time_msc = ExtractJsonLong(resp_str, "acknowledged_time_msc");
      ack_deal_ticket = ExtractJsonLong(resp_str, "acknowledged_deal_ticket");
   }
   
   return http_code;
}
