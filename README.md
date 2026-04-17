# DataOps Agent - AI Database Operations

A multi-agent system for autonomous database operations built with AWS Strands Agents SDK, Amazon Bedrock, and a React UI.

Inspired by the [AWS Builder Session: Building Your First AI Database Ops Agent](https://lets-talk-about-data-aws.com/catch-up-s0411).

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  React UI (Vite)                │
│  Chat Interface │ Health Dashboard │ Action Log  │
└──────────────────────┬──────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────┐
│              FastAPI Backend                     │
│  /chat  /health  /actions  /stream              │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│           Supervisor Agent (Strands)            │
│  ┌─────────────┐  ┌──────────────┐              │
│  │ HealthCheck  │  │   Action     │              │
│  │   Agent      │  │   Agent      │              │
│  └──────┬──────┘  └──────┬───────┘              │
│         │                │                       │
│  Tools: │         Tools: │                       │
│  - largest_tables  - create_index_concurrently  │
│  - unused_indexes  - analyze_table              │
│  - table_bloat     - vacuum_table               │
│  - index_bloat     - list_clusters              │
│  - top_queries                                   │
└──────────────────────┬──────────────────────────┘
                       │
              Aurora PostgreSQL
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- AWS credentials configured with Bedrock access (Claude Sonnet)
- PostgreSQL database (Aurora or local)

## Quick Start

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # edit with your DB and AWS settings
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Environment Variables

See `backend/.env.example` for all configuration options.
