# TradeDNA — Exness Trading Intelligence Platform

> **Decode Your Trading. Understand Your Edge.**

TradeDNA is an enterprise-grade, Exness-exclusive, read-only trading intelligence platform. It connects to live Exness MetaTrader 5 trading accounts through an authenticated read-only MQL5 connector, validates raw event streams into an append-only dual-layer canonical financial ledger, and calculates deterministic quantitative and behavioral analytics paired with a verifiable **Trading DNA** profile.

---

## 🏛 Monorepo Architecture

```
tradedna/
├── apps/
│   ├── api/                    # Python FastAPI Backend
│   └── web/                    # Next.js 14+ Frontend (TypeScript, Tailwind CSS, shadcn/ui)
├── connectors/
│   └── mt5/                    # MQL5 Read-Only Expert Advisor Connector
└── docker-compose.yml          # Infrastructure orchestration (FastAPI, PostgreSQL 16, Redis 7)
```

---

## 🚀 Quick Start

### 1. Backend Setup
```bash
cd apps/api
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
cp ../../.env.example .env
pytest
uvicorn src.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd apps/web
npm install
npm run dev
```

### 3. Docker Compose (Full Stack)
```bash
docker-compose up -d
```
