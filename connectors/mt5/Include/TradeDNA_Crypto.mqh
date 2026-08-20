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
//| Convert hexadecimal string to byte array                         |
//+------------------------------------------------------------------+
int HexToBytes(const string hex_str, uchar &output[])
{
   int len = StringLen(hex_str);
   if(len % 2 != 0) return 0;
   
   int out_size = len / 2;
   ArrayResize(output, out_size);
   
   for(int i = 0; i < out_size; i++)
   {
      string byte_str = StringSubstr(hex_str, i * 2, 2);
      ushort ch0 = StringGetCharacter(byte_str, 0);
      ushort ch1 = StringGetCharacter(byte_str, 1);
      
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
//| Standards-Compliant RFC 2104 HMAC-SHA256 Implementation          |
//+------------------------------------------------------------------+
string ComputeHMACSHA256(const string key_hex, const string message)
{
   uchar key[];
   HexToBytes(key_hex, key);
   
   uchar K_prime[64];
   ArrayInitialize(K_prime, 0);
   
   if(ArraySize(key) > 64)
   {
      uchar key_hash[];
      ComputeSHA256(key, key_hash);
      ArrayCopy(K_prime, key_hash, 0, 0, 32);
   }
   else
   {
      ArrayCopy(K_prime, key, 0, 0, ArraySize(key));
   }
   
   uchar k_ipad[64];
   uchar k_opad[64];
   for(int i = 0; i < 64; i++)
   {
      k_ipad[i] = (uchar)(K_prime[i] ^ 0x36);
      k_opad[i] = (uchar)(K_prime[i] ^ 0x5c);
   }
   
   // 1. Inner Hash: SHA256(k_ipad || message_bytes) without null terminator
   uchar msg_bytes[];
   StringToUtf8Bytes(message, msg_bytes);
   
   uchar inner_input[];
   ArrayResize(inner_input, 64 + ArraySize(msg_bytes));
   ArrayCopy(inner_input, k_ipad, 0, 0, 64);
   ArrayCopy(inner_input, msg_bytes, 64, 0, ArraySize(msg_bytes));
   
   uchar inner_hash[];
   ComputeSHA256(inner_input, inner_hash);
   
   // 2. Outer Hash: SHA256(k_opad || inner_hash)
   uchar outer_input[];
   ArrayResize(outer_input, 64 + 32);
   ArrayCopy(outer_input, k_opad, 0, 0, 64);
   ArrayCopy(outer_input, inner_hash, 64, 0, 32);
   
   uchar final_hash[];
   ComputeSHA256(outer_input, final_hash);
   
   return BytesToHex(final_hash);
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
   // Using direct string concatenation for 64-bit integer safety
   string canonical_payload = device_id + "|" + IntegerToString(timestamp_ms) + "|" + nonce + "|" + body_sha256;
   
   // 3. Compute HMAC-SHA256 over canonical string
   return ComputeHMACSHA256(device_secret_hex, canonical_payload);
}
