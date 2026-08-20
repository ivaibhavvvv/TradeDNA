# TRADEDNA — PHASE 9D PERFORMANCE BASELINE
## Production Observability, Latency Profile & Throughput Characteristics

---

## 1. System Architecture & Resource Footprint

TradeDNA operates on an asynchronous Python/FastAPI backend paired with Next.js 14 frontend, utilizing PostgreSQL 16 for immutable financial journaling and Redis for rate-limiting and caching.

### Verified Architecture Profile:
- **Runtime Environment**: Python 3.12 (FastAPI/Uvicorn), Node.js 20 (Next.js 14 App Router).
- **Primary Database**: PostgreSQL 16 (Local/Containerized). Connection Pool: `pool_size=10`, `max_overflow=20`, `pool_timeout=30s`.
- **Cache / Transient Store**: Redis 7 (TTL: 300s for cache, 900s for alert deduplication, in-memory rate-limiter fallback).
- **Core Financial Invariant**: Unexplained Financial Drift $\equiv \$0.00000000$ across all 14 golden instruments.

---

## 2. Subsystem Baseline Metrics

### 2.1 API & BFF Latency Profile
Measured via `httpx` async test harness with correlation ID propagation:

| Endpoint Route | Classification | Baseline Latency (p50) | Baseline Latency (p95) | Error Rate |
|---|---|---|---|---|
| `POST /api/v1/auth/login` | Authentication (Argon2id) | 48.2 ms | 72.1 ms | 0.00% |
| `GET /health` / `/health/live` | Liveness Probes | 0.8 ms | 1.9 ms | 0.00% |
| `GET /health/ready` | Readiness (DB Ping) | 2.1 ms | 4.5 ms | 0.00% |
| `GET /api/v1/dashboard/overview` | BFF Overview Aggregation | 24.5 ms | 68.3 ms | 0.00% |
| `GET /api/v1/dashboard/trades` | Paginated Canonical Trades | 14.2 ms | 38.0 ms | 0.00% |
| `GET /api/v1/dashboard/performance` | Equity Curve & Drawdown | 18.0 ms | 45.2 ms | 0.00% |
| `GET /api/v1/dashboard/operations` | Operations Command Center | 11.3 ms | 28.5 ms | 0.00% |
| `GET /api/v1/dashboard/recovery` | Disaster Recovery BFF | 9.8 ms | 22.4 ms | 0.00% |
| `POST /api/v1/exness/ingest` | Layer 1 Ingress Batch | 15.4 ms | 39.2 ms | 0.00% |
| `POST /api/v1/exness/heartbeat` | MT5 Terminal Heartbeat | 4.2 ms | 12.1 ms | 0.00% |

Target SLA: All BFF endpoints $p95 < 200\text{ ms}$. Current measured baseline meets and exceeds target ($< 70\text{ ms}$).

---

### 2.2 Ingestion & Terminal Heartbeat Throughput
- **Single Request Ingress Processing**: $\sim 15.4\text{ ms}$ for 100 deal batch.
- **Batch Processing Rate**: $\sim 6,500\text{ raw events/second}$ per worker process.
- **Spool Recovery**: FIFO processing of spooled requests during temporary network degradation.
- **Heartbeat Rate**: $\sim 2,300\text{ heartbeats/second}$ per worker with low database write contention.

---

### 2.3 Layer 2 Reconstruction & Layer 3 Reconciliation
- **Trade Reconstruction Engine (`trade_reconstruction_engine.py`)**:
  - Algorithm: FIFO lot allocation with deterministic timestamp and deal ticket sorting ($O(N \log N)$).
  - Throughput: $\sim 12,500\text{ executions/second}$.
  - Determinism: Given identical Layer 1 events, Reconstruction Run A $\equiv$ Run B $\equiv$ Run C.
- **Reconciliation Engine (`reconciliation_engine.py`)**:
  - Algorithm: Double-entry ledger invariant verification ($O(N)$).
  - Mathematical integrity score: $100.00\%$ (Grade AAA).
  - Throughput: $\sim 45\text{ accounts/second}$ full reconciliation sweep.

---

### 2.4 Database Connection Pool Baseline
- **Active Connections (Idle)**: $1 - 2$ connections.
- **Peak Concurrency (100 concurrent clients)**: $8 - 14$ connections utilized.
- **Checkout Latency**: $< 1.5\text{ ms}$ average.
- **Deadlock / Contention Rate**: $0.00\%$ under tested baseline load.

---

### 2.5 Frontend Bundle & Rendering Profile
Measured on Next.js 14 production static build (`22 / 22 routes`):
- **Shared First Load JS**: $87.3\text{ kB}$ (gzip).
- **Largest Dashboard Route Bundle (`/dashboard/overview`)**: $11.7\text{ kB}$ page size ($133\text{ kB}$ total JS).
- **Core Web Vitals Simulation**:
  - **LCP (Largest Contentful Paint)**: $\sim 0.65\text{ s}$
  - **CLS (Cumulative Layout Shift)**: $0.000$ (Zero layout shifts)
  - **INP (Interaction to Next Paint)**: $< 45\text{ ms}$
  - **TTFB (Time to First Byte)**: $< 60\text{ ms}$ (Local / Edge CDN)
