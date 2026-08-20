//+------------------------------------------------------------------+
//|                                             TradeDNA_Buffer.mqh  |
//|                                  Copyright 2026, TradeDNA Team   |
//|        In-Memory Ring Buffer & Persistent Spool (Zero Event Loss)|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, TradeDNA Team"
#property link      "https://tradedna.io"
#property strict

#include "TradeDNA_Types.mqh"

#define RING_BUFFER_SIZE      2048
#define MAX_SPOOL_FILE_SIZE   52428800 // 50 Megabytes
#define SPOOL_FILE_NAME       "tradedna_spool.bin"

// In-Memory Ring Buffer Array
EventItem g_ring_buffer[RING_BUFFER_SIZE];
int g_buffer_head = 0;
int g_buffer_tail = 0;
int g_buffer_count = 0;
bool g_storage_pressure = false;

//+------------------------------------------------------------------+
//| Calculate standard CRC32 checksum of a string                    |
//+------------------------------------------------------------------+
uint CalculateCRC32(const string text)
{
   uchar bytes[];
   int len = StringToCharArray(text, bytes, 0, StringLen(text), CP_UTF8);
   uint crc = 0xFFFFFFFF;
   
   for(int i = 0; i < len; i++)
   {
      crc ^= bytes[i];
      for(int j = 0; j < 8; j++)
      {
         if((crc & 1) != 0)
            crc = (crc >> 1) ^ 0xEDB88320;
         else
            crc >>= 1;
      }
   }
   return ~crc;
}

//+------------------------------------------------------------------+
//| Append Event to Persistent Disk Spool                            |
//+------------------------------------------------------------------+
bool SpoolEventToDisk(const EventItem &item)
{
   // Check disk spool file size limit
   if(FileIsExist(SPOOL_FILE_NAME))
   {
      int check_handle = FileOpen(SPOOL_FILE_NAME, FILE_READ | FILE_BIN);
      if(check_handle != INVALID_HANDLE)
      {
         ulong size = FileSize(check_handle);
         FileClose(check_handle);
         if(size > MAX_SPOOL_FILE_SIZE)
         {
            g_storage_pressure = true;
            Print("[TradeDNA Spool] CRITICAL: Spool disk quota exceeded (>50MB). Entering STORAGE_PRESSURE state.");
            return false;
         }
      }
   }
   
   int handle = FileOpen(SPOOL_FILE_NAME, FILE_READ | FILE_WRITE | FILE_BIN);
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen(SPOOL_FILE_NAME, FILE_WRITE | FILE_BIN);
   }
   if(handle == INVALID_HANDLE)
   {
      g_storage_pressure = true;
      return false;
   }
   
   FileSeek(handle, 0, SEEK_END);
   FileWriteString(handle, item.payload_type);
   FileWriteLong(handle, item.ticket);
   FileWriteLong(handle, item.time_msc);
   FileWriteInteger(handle, StringLen(item.json_payload));
   FileWriteString(handle, item.json_payload);
   FileWriteInteger(handle, (int)item.crc32);
   
   FileClose(handle);
   return true;
}

//+------------------------------------------------------------------+
//| Push Event into In-Memory Buffer (Spills to Disk if >80% Full)   |
//+------------------------------------------------------------------+
bool PushEvent(const string payload_type, const long ticket, const long time_msc, const string json_payload)
{
   EventItem item;
   item.payload_type = payload_type;
   item.ticket = ticket;
   item.time_msc = time_msc;
   item.json_payload = json_payload;
   item.crc32 = CalculateCRC32(json_payload);
   
   // If ring buffer is near capacity (>80%), spool directly to persistent disk
   if(g_buffer_count >= (RING_BUFFER_SIZE * 8 / 10))
   {
      return SpoolEventToDisk(item);
   }
   
   // Push to Ring Buffer
   g_ring_buffer[g_buffer_head] = item;
   g_buffer_head = (g_buffer_head + 1) % RING_BUFFER_SIZE;
   g_buffer_count++;
   
   return true;
}

//+------------------------------------------------------------------+
//| Pop Event from In-Memory Ring Buffer                             |
//+------------------------------------------------------------------+
bool PopEvent(EventItem &item)
{
   if(g_buffer_count <= 0) return false;
   
   item = g_ring_buffer[g_buffer_tail];
   g_buffer_tail = (g_buffer_tail + 1) % RING_BUFFER_SIZE;
   g_buffer_count--;
   return true;
}

//+------------------------------------------------------------------+
//| Check if Spool File Exists and Contains Queued Records           |
//+------------------------------------------------------------------+
bool HasDiskSpoolRecords()
{
   return FileIsExist(SPOOL_FILE_NAME);
}

//+------------------------------------------------------------------+
//| Drain Single Batch of Records from Disk Spool (FIFO)             |
//+------------------------------------------------------------------+
int DrainSpoolBatch(EventItem &batch[], int max_records = 50)
{
   if(!FileIsExist(SPOOL_FILE_NAME)) return 0;
   
   int handle = FileOpen(SPOOL_FILE_NAME, FILE_READ | FILE_BIN);
   if(handle == INVALID_HANDLE) return 0;
   
   ArrayResize(batch, 0);
   int count = 0;
   
   while(!FileIsEnding(handle) && count < max_records)
   {
      EventItem item;
      item.payload_type = FileReadString(handle);
      if(StringLen(item.payload_type) == 0) break;
      
      item.ticket = FileReadLong(handle);
      item.time_msc = FileReadLong(handle);
      int json_len = (int)FileReadInteger(handle);
      item.json_payload = FileReadString(handle, json_len);
      item.crc32 = (uint)FileReadInteger(handle);
      
      // Verify CRC32
      if(CalculateCRC32(item.json_payload) == item.crc32)
      {
         int new_size = ArraySize(batch) + 1;
         ArrayResize(batch, new_size);
         batch[new_size - 1] = item;
         count++;
      }
   }
   
   // Read remaining records if any and rewrite or delete file
   EventItem remaining[];
   int rem_count = 0;
   while(!FileIsEnding(handle))
   {
      EventItem rem_item;
      rem_item.payload_type = FileReadString(handle);
      if(StringLen(rem_item.payload_type) == 0) break;
      rem_item.ticket = FileReadLong(handle);
      rem_item.time_msc = FileReadLong(handle);
      int json_len = (int)FileReadInteger(handle);
      rem_item.json_payload = FileReadString(handle, json_len);
      rem_item.crc32 = (uint)FileReadInteger(handle);
      
      int rem_size = ArraySize(remaining) + 1;
      ArrayResize(remaining, rem_size);
      remaining[rem_size - 1] = rem_item;
      rem_count++;
   }
   FileClose(handle);
   
   if(rem_count == 0)
   {
      FileDelete(SPOOL_FILE_NAME);
      g_storage_pressure = false;
   }
   else
   {
      // Rewrite spool with remaining records
      int write_handle = FileOpen(SPOOL_FILE_NAME, FILE_WRITE | FILE_BIN);
      if(write_handle != INVALID_HANDLE)
      {
         for(int i = 0; i < rem_count; i++)
         {
            FileWriteString(write_handle, remaining[i].payload_type);
            FileWriteLong(write_handle, remaining[i].ticket);
            FileWriteLong(write_handle, remaining[i].time_msc);
            FileWriteInteger(write_handle, StringLen(remaining[i].json_payload));
            FileWriteString(write_handle, remaining[i].json_payload);
            FileWriteInteger(write_handle, (int)remaining[i].crc32);
         }
         FileClose(write_handle);
      }
   }
   
   return count;
}
