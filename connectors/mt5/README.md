# TradeDNA MT5 Connector (MQL5)

## Overview
The `TradeDNAConnector.mq5` is a strictly **read-only** Expert Advisor (EA) designed for authenticated Exness MetaTrader 5 accounts.

---

## Non-Negotiable Invariants
1. **Zero Execution**: The connector contains NO calls to `OrderSend`, `OrderSendAsync`, `PositionClose`, or order modification endpoints.
2. **Read-Only Data Acquisition**: Ingests account state (`AccountInfoDouble`), historical deals (`HistorySelect`), and open position summaries for informational display.
3. **Cryptographic Signing**: Payloads are signed with `HMAC-SHA256` using device secrets exchanged via a one-time pairing token.
4. **Append-Only Transmission**: Transmits chunked batches with `X-TradeDNA-Timestamp` and `X-TradeDNA-Nonce` for replay protection.

---

## Directory Structure
```
connectors/mt5/
├── TradeDNAConnector.mq5      # MQL5 Read-Only EA Source (Phase 3)
├── README.md                  # Installation & Architecture Guide
├── installation/              # Step-by-step PDF / Markdown installation guides
└── config/                    # Default terminal configuration templates
```
