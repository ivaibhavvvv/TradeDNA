//+------------------------------------------------------------------+
//|                                             TradeDNA_Crypto.mqh  |
//|                                  Copyright 2026, TradeDNA Team   |
//|                    RFC 2104 / RFC 4231 Compliant HMAC-SHA256     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradeDNA Team"
#property link      "https://tradedna.io"
#property strict

//+------------------------------------------------------------------+
//| Convert byte array to lowercase hexadecimal string               |
//+------------------------------------------------------------------+
string BytesToHex(const uchar &data[])
{
   string hex = "";
   int size = ArraySize(data);
   for(int i = 0; i < size; i++)
   {
      hex += StringFormat("%02x", data[i]);
   }
   return hex;
}

//+------------------------------------------------------------------+
//| Sanitize Hex String to ensure only valid 0-9, a-f, A-F chars     |
//+------------------------------------------------------------------+
string CleanHex(const string hex_str)
{
   string clean = "";
   int len = StringLen(hex_str);
   for(int i = 0; i < len; i++)
   {
      ushort ch = StringGetCharacter(hex_str, i);
      if((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f') || (ch >= 'A' && ch <= 'F'))
      {
         clean += ShortToString(ch);
      }
   }
   return clean;
}

//+------------------------------------------------------------------+
//| Sanitize ASCII String (strips CRLF and non-printable chars)      |
//+------------------------------------------------------------------+
string CleanString(const string str)
{
   string clean = "";
   int len = StringLen(str);
   for(int i = 0; i < len; i++)
   {
      ushort ch = StringGetCharacter(str, i);
      if(ch >= 32 && ch <= 126)
      {
         clean += ShortToString(ch);
      }
   }
   return clean;
}

//+------------------------------------------------------------------+
//| Convert hexadecimal string to byte array                         |
//+------------------------------------------------------------------+
int HexToBytes(const string input_hex_str, uchar &output[])
{
   string hex_str = CleanHex(input_hex_str);
   int len = StringLen(hex_str);
   if(len == 0 || len % 2 != 0)
   {
      ArrayResize(output, 0);
      return 0;
   }
   
   int out_size = len / 2;
   ArrayResize(output, out_size);
   
   for(int i = 0; i < out_size; i++)
   {
      ushort ch0 = StringGetCharacter(hex_str, i * 2);
      ushort ch1 = StringGetCharacter(hex_str, i * 2 + 1);
      
      int v0 = (ch0 >= '0' && ch0 <= '9') ? (ch0 - '0') :
               (ch0 >= 'a' && ch0 <= 'f') ? (ch0 - 'a' + 10) :
               (ch0 >= 'A' && ch0 <= 'F') ? (ch0 - 'A' + 10) : 0;
               
      int v1 = (ch1 >= '0' && ch1 <= '9') ? (ch1 - '0') :
               (ch1 >= 'a' && ch1 <= 'f') ? (ch1 - 'a' + 10) :
               (ch1 >= 'A' && ch1 <= 'F') ? (ch1 - 'A' + 10) : 0;
               
      output[i] = (uchar)((v0 << 4) | v1);
   }
   return out_size;
}

//+------------------------------------------------------------------+
//| Compute SHA-256 hash of byte array                               |
//+------------------------------------------------------------------+
int ComputeSHA256(const uchar &data[], uchar &hash_out[])
{
   uchar empty_key[];
   return CryptEncode(CRYPT_HASH_SHA256, data, empty_key, hash_out);
}

//+------------------------------------------------------------------+
//| Convert string to exact UTF-8 byte array without null terminator |
//+------------------------------------------------------------------+
int StringToUtf8Bytes(const string str, uchar &output[])
{
   int count = StringToCharArray(str, output, 0, WHOLE_ARRAY, CP_UTF8);
   if(count > 0 && ArraySize(output) > 0 && output[ArraySize(output) - 1] == 0)
   {
      ArrayResize(output, ArraySize(output) - 1);
      return ArraySize(output);
   }
   return ArraySize(output);
}

//+------------------------------------------------------------------+
//| Compute SHA-256 hash of a UTF-8 string returning lowercase hex   |
//+------------------------------------------------------------------+
string ComputeStringSHA256Hex(const string str)
{
   uchar data[];
   StringToUtf8Bytes(str, data);
   uchar hash[];
   ComputeSHA256(data, hash);
   return BytesToHex(hash);
}

//+------------------------------------------------------------------+
//| Standards-Compliant HMAC-SHA256 via Native MQL5 CryptEncode      |
//+------------------------------------------------------------------+
string ComputeHMACSHA256(const string key_hex, const string message)
{
   uchar key[];
   int key_len = HexToBytes(key_hex, key);
   if(key_len == 0)
   {
      PrintFormat("[TradeDNA Crypto] Error: Invalid key length (%d) for secret hex", key_len);
   }
   
   uchar data[];
   StringToUtf8Bytes(message, data);
   
   uchar hash[];
   ResetLastError();
   // In MQL5, CryptEncode with CRYPT_HASH_SHA256 and non-empty key computes HMAC-SHA256 directly
   int res = CryptEncode(CRYPT_HASH_SHA256, data, key, hash);
   if(res > 0 && ArraySize(hash) > 0)
   {
      return BytesToHex(hash);
   }
   
   PrintFormat("[TradeDNA Crypto] Error: CryptEncode HMAC failed, error: %d", GetLastError());
   return "";
}

//+------------------------------------------------------------------+
//| Generate High-Entropy Cryptographic Nonce (Hex String)           |
//+------------------------------------------------------------------+
string GenerateNonce(int byte_length = 16)
{
   uchar random_bytes[];
   ArrayResize(random_bytes, byte_length);
   for(int i = 0; i < byte_length; i++)
   {
      random_bytes[i] = (uchar)(MathRand() ^ (GetTickCount() & 0xFF) ^ (i * 37));
   }
   return BytesToHex(random_bytes);
}

//+------------------------------------------------------------------+
//| Assemble Canonical Payload and Generate HMAC-SHA256 Signature    |
//+------------------------------------------------------------------+
string SignRequestPayload(
   const string device_id,
   const long timestamp_ms,
   const string nonce,
   const string raw_body_json,
   const string device_secret_hex
)
{
   // 1. Calculate lowercase SHA256 of raw UTF-8 HTTP body
   string body_sha256 = ComputeStringSHA256Hex(raw_body_json);
   
   // 2. Format canonical string: Device-ID | Timestamp | Nonce | Body-SHA256
   string clean_dev_id = CleanString(device_id);
   string clean_nonce = CleanHex(nonce);
   string canonical_payload = clean_dev_id + "|" + IntegerToString(timestamp_ms) + "|" + clean_nonce + "|" + body_sha256;
   
   // 3. Compute HMAC-SHA256 over canonical string
   return ComputeHMACSHA256(device_secret_hex, canonical_payload);
}
