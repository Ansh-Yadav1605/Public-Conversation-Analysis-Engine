# Deployment Plan — Public Conversation Analysis Engine

> **Backend → Railway** | **Frontend → Vercel**
> **Repo:** `Ansh-Yadav1605/Public-Conversation-Analysis-Engine`
> **Last Updated:** 2026-08-17

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture — Deployed](#2-architecture--deployed)
3. [What Needs to Be Built First](#3-what-needs-to-be-built-first)
4. [Phase A — Backend API (Railway)](#4-phase-a--backend-api-railway)
5. [Phase B — Frontend Dashboard (Vercel)](#5-phase-b--frontend-dashboard-vercel)
6. [Environment Variables](#6-environment-variables)
7. [File & Directory Changes Required](#7-file--directory-changes-required)
8. [Railway Deployment — Step by Step](#8-railway-deployment--step-by-step)
9. [Vercel Deployment — Step by Step](#9-vercel-deployment--step-by-step)
10. [CI/CD — GitHub Actions](#10-cicd--github-actions)
11. [Post-Deployment Checklist](#11-post-deployment-checklist)
12. [Cost Estimate](#12-cost-estimate)

---

## 1. System Overview

The engine today is a **CLI-only Python pipeline** that runs end-to-end locally:

```
python run_pipeline.py → scrape → extract → analyze → export (JSON / MD / CSV)
```

To deploy it, we need to split it into two deployed layers:

| Layer | Responsibility | Platform |
|---|---|---|
| **Backend API** | Run the pipeline on demand, serve results, manage job state | Railway |
| **Frontend Dashboard** | Trigger pipeline runs, display ranked opportunities, view evidence | Vercel |

---

## 2. Architecture — Deployed

```
┌─────────────────────────────────────────────────────────────┐
│                    Vercel (Frontend)                        │
│                                                             │
│   Next.js Dashboard                                         │
│   ┌──────────────┐  ┌────────────────┐  ┌───────────────┐  │
│   │  Run Pipeline│  │ Opportunity    │  │ Signal        │  │
│   │  Trigger UI  │  │ Rankings View  │  │ Evidence View │  │
│   └──────┬───────┘  └───────┬────────┘  └───────┬───────┘  │
│          │                  │                    │          │
└──────────┼──────────────────┼────────────────────┼──────────┘
           │  REST API calls  │                    │
           ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Railway (Backend)                        │
│                                                             │
│   FastAPI Application                                       │
│   ┌──────────────┐  ┌────────────────┐  ┌───────────────┐  │
│   │  POST /run   │  │ GET /results   │  │ GET /signals  │  │
│   │  (triggers   │  │ (opportunities)│  │ (raw signals) │  │
│   │   pipeline)  │  │                │  │               │  │
│   └──────┬───────┘  └───────┬────────┘  └───────┬───────┘  │
│          │                  │                    │          │
│          ▼                  ▼                    ▼          │
│   ┌─────────────────────────────────────────────────────┐  │
│   │         Engine Pipeline (run_pipeline.py)           │  │
│   │   Phase 2 → Phase 3 → Phase 4 → Phase 5            │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │   Persistent Volume (Railway)                       │  │
│   │   engine/data/  (raw_records, signals, opps)        │  │
│   └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. What Needs to Be Built First

> [!IMPORTANT]
> The engine currently has **no HTTP API layer** and **no frontend**. Both must be built before deployment. This plan defines exactly what to build and in what order.

### 3.1 Backend — Needs to Be Added

| Item | Status | Notes |
|---|---|---|
| `api/main.py` — FastAPI app | ❌ Not built | New file needed |
| `api/routes/pipeline.py` — run endpoint | ❌ Not built | Wraps `run_full_pipeline()` |
| `api/routes/results.py` — read results | ❌ Not built | Reads from opportunity/signal stores |
| `Procfile` | ❌ Not built | Tells Railway how to start the app |
| `railway.json` | ❌ Not built | Railway service config |
| `runtime.txt` | ❌ Not built | Pins Python version |

### 3.2 Frontend — Needs to Be Built

| Item | Status | Notes |
|---|---|---|
| Next.js app (`/frontend`) | ❌ Not built | New directory needed |
| Dashboard page | ❌ Not built | Trigger + ranked results view |
| Opportunity cards | ❌ Not built | Ranked list with score bars |
| Evidence drawer | ❌ Not built | Verbatim quotes + source links |

---

## 4. Phase A — Backend API (Railway)

### 4.1 Directory Structure to Create

```
/ (repo root)
├── api/
│   ├── __init__.py
│   ├── main.py                  ← FastAPI app entry point
│   └── routes/
│       ├── __init__.py
│       ├── pipeline.py          ← POST /api/run, GET /api/status/{job_id}
│       └── results.py           ← GET /api/results, GET /api/signals
├── Procfile                     ← start command for Railway
├── railway.json                 ← Railway service config
└── runtime.txt                  ← python-3.11.x
```

### 4.2 Key API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check for Railway uptime monitoring |
| `POST` | `/api/run` | Trigger a full pipeline run (async background task) |
| `GET` | `/api/status/{job_id}` | Poll job: `pending → running → done / failed` |
| `GET` | `/api/results` | Return ranked `OpportunityArea[]` from last run |
| `GET` | `/api/signals` | Return all `Signal[]` records for evidence view |
| `GET` | `/api/config` | Return current taxonomy & question set (read-only) |

### 4.3 Background Job Strategy

Railway does not require Redis for the graduation project scale. Use FastAPI's built-in `BackgroundTasks` with an in-memory job store:

```python
# api/routes/pipeline.py (skeleton)
from fastapi import APIRouter, BackgroundTasks
import uuid

router = APIRouter()
jobs: dict = {}  # in-memory; fine for single-instance Railway deployment

@router.post("/run")
async def trigger_run(background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending"}
    background_tasks.add_task(_run_pipeline_task, job_id)
    return {"job_id": job_id}

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})

async def _run_pipeline_task(job_id: str):
    jobs[job_id] = {"status": "running"}
    try:
        from run_pipeline import run_full_pipeline
        summary = run_full_pipeline()
        jobs[job_id] = {"status": "done", "summary": summary}
    except Exception as e:
        jobs[job_id] = {"status": "failed", "error": str(e)}
```

> [!NOTE]
> For production beyond the graduation project, upgrade to Railway's Redis add-on and use `celery` for proper durable task queuing.

### 4.4 `Procfile`

```
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

### 4.5 `railway.json`

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r engine/requirements.txt fastapi uvicorn[standard]"
  },
  "deploy": {
    "startCommand": "uvicorn api.main:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

### 4.6 `runtime.txt`

```
python-3.11.9
```

### 4.7 Persistent Storage on Railway

The pipeline writes to `engine/data/` (raw records, signals, opportunities). Use a Railway **Volume** to persist this between deployments.

Steps:
1. Railway dashboard → your service → **Volumes** tab
2. Create volume, mount path: `/app/engine/data`
3. Set env var `ENGINE_DATA_DIR=/app/engine/data` so the pipeline uses it

### 4.8 CORS Configuration

Add this to `api/main.py` so the Vercel frontend can call the Railway backend:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-project.vercel.app",
        "http://localhost:3000",   # local dev
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 5. Phase B — Frontend Dashboard (Vercel)

### 5.1 Stack

| Tool | Purpose |
|---|---|
| **Next.js 14** (App Router) | Framework |
| **Tailwind CSS** | Styling |
| **Recharts** | Score visualization bars |
| **Native fetch / axios** | API calls to Railway backend |

### 5.2 Directory Structure

```
/frontend
├── app/
│   ├── layout.tsx
│   ├── page.tsx                   ← Dashboard: trigger + ranked list
│   ├── opportunities/
│   │   └── [id]/page.tsx          ← Detail: score breakdown + evidence quotes
│   └── signals/
│       └── page.tsx               ← Raw signal explorer (filterable table)
├── components/
│   ├── OpportunityCard.tsx        ← Ranked card with composite score bar
│   ├── ScoreBar.tsx               ← Frequency / Severity / Evidence bars
│   ├── SignalTable.tsx            ← Filterable signal log
│   ├── RunPipelineButton.tsx      ← Triggers POST /api/run
│   └── JobStatusBadge.tsx         ← Polls GET /api/status/{job_id}
├── lib/
│   └── api.ts                     ← Typed API client (Railway URL from env)
├── .env.local                     ← NEXT_PUBLIC_API_URL=http://localhost:8000
├── next.config.ts
└── vercel.json
```

### 5.3 `vercel.json`

```json
{
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "installCommand": "npm install"
}
```

### 5.4 Key Pages

| Page | Route | What It Shows |
|---|---|---|
| **Dashboard** | `/` | Run button, job status, ranked opportunity cards |
| **Opportunity Detail** | `/opportunities/[id]` | Score breakdown, segment note, verbatim quotes with source links |
| **Signal Explorer** | `/signals` | Full signal table filterable by dimension / source / severity |

---

## 6. Environment Variables

### 6.1 Railway (Backend) — set in Railway dashboard → Variables

| Variable | Value | Where to Get It |
|---|---|---|
| `REDDIT_CLIENT_ID` | Your Reddit app client ID | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | Your Reddit app secret | Same |
| `REDDIT_USER_AGENT` | `engine:v0.1 (by /u/your_username)` | Custom string |
| `TWITTER_BEARER_TOKEN` | Twitter Bearer Token | [developer.twitter.com](https://developer.twitter.com) |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key | [Google Cloud Console](https://console.cloud.google.com) |
| `PYTHONPATH` | `/app` | Ensures `engine` package is importable |
| `ENGINE_DATA_DIR` | `/app/engine/data` | Points pipeline to Railway Volume |
| `PORT` | Auto-set by Railway | — |

### 6.2 Vercel (Frontend) — set in Vercel dashboard → Settings → Environment Variables

| Variable | Production Value | Development Value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://your-service.railway.app` | `http://localhost:8000` |

---

## 7. File & Directory Changes Required

### 7.1 New Files to Create

```
api/__init__.py
api/main.py
api/routes/__init__.py
api/routes/pipeline.py
api/routes/results.py
Procfile
railway.json
runtime.txt
frontend/                    ← scaffold via npx create-next-app
.github/workflows/deploy.yml
```

### 7.2 Existing Files to Modify

| File | Change Needed |
|---|---|
| [`run_pipeline.py`](file:///c:/Users/anshy/OneDrive/Desktop/Graduation%20Project_PM/run_pipeline.py) | Make `DEFAULT_REPORTS_DIR` read from `ENGINE_DATA_DIR` env var |
| [`engine/data_store.py`](file:///c:/Users/anshy/OneDrive/Desktop/Graduation%20Project_PM/engine/data_store.py) | Make data paths respect `ENGINE_DATA_DIR` env var |
| [`.env.example`](file:///c:/Users/anshy/OneDrive/Desktop/Graduation%20Project_PM/.env.example) | Add `ENGINE_DATA_DIR`, `PYTHONPATH` |
| [`.gitignore`](file:///c:/Users/anshy/OneDrive/Desktop/Graduation%20Project_PM/.gitignore) | Add `frontend/.next/`, `frontend/node_modules/` |

### 7.3 Files That Do NOT Need Changes

- All `engine/scraper/`, `engine/extractor/`, `engine/analyzer/` core logic — deploy as-is
- All `engine/config/*.yaml` — baked into the container image
- `engine/pyproject.toml` — no changes needed

---

## 8. Railway Deployment — Step by Step

### Step 1 — Build the API Layer
```
Create: api/main.py, api/routes/pipeline.py, api/routes/results.py
```

### Step 2 — Add Root Config Files
```
Create: Procfile, railway.json, runtime.txt  (see Section 4.4 – 4.6)
```

### Step 3 — Create a Railway Project
1. Go to [railway.app](https://railway.app) → **New Project**
2. Choose **Deploy from GitHub repo**
3. Select `Ansh-Yadav1605/Public-Conversation-Analysis-Engine`
4. Railway auto-detects Python via Nixpacks

### Step 4 — Set Environment Variables
Dashboard → your service → **Variables** tab → add all vars from Section 6.1.

> [!IMPORTANT]
> `PYTHONPATH=/app` is critical — without it, `from engine.xxx import ...` will fail at runtime.

### Step 5 — Attach a Volume
1. Service → **Volumes** tab
2. Mount path: `/app/engine/data`
3. Persists scraped data and pipeline outputs between restarts

### Step 6 — Deploy & Test
```bash
# Railway auto-deploys on push to main branch.
# Check: Dashboard → Deployments → View Logs

# Verify health check
curl https://your-service.railway.app/health
# Expected: {"status": "ok", "version": "0.1.0"}

# Trigger a test run
curl -X POST https://your-service.railway.app/api/run
# Expected: {"job_id": "some-uuid"}
```

### Step 7 — Copy the Railway URL
You'll need it (e.g. `https://public-conversation-engine.up.railway.app`) for Vercel setup.

---

## 9. Vercel Deployment — Step by Step

### Step 1 — Scaffold the Frontend
```bash
cd "c:\Users\anshy\OneDrive\Desktop\Graduation Project_PM"
npx create-next-app@latest frontend --typescript --tailwind --app --no-src-dir
```

### Step 2 — Build Pages & Components
Implement the pages and components described in Section 5.2.

### Step 3 — Set Local Environment
```
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Step 4 — Test Locally
```bash
# Terminal 1 — run backend
cd "c:\Users\anshy\OneDrive\Desktop\Graduation Project_PM"
uvicorn api.main:app --reload --port 8000

# Terminal 2 — run frontend
cd frontend
npm run dev
# → http://localhost:3000
```

### Step 5 — Deploy to Vercel

**Option A — Vercel CLI (recommended):**
```bash
npm i -g vercel
cd frontend
vercel --prod
```

**Option B — Vercel Dashboard:**
1. [vercel.com](https://vercel.com) → **New Project**
2. Import from GitHub → select same repo
3. Set **Root Directory** to `frontend`
4. Deploy

### Step 6 — Set Production Environment Variable
Vercel → project → **Settings → Environment Variables**:
```
NEXT_PUBLIC_API_URL = https://your-service.railway.app
```
Redeploy for the variable to take effect.

---

## 10. CI/CD — GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install & Build Frontend
        run: |
          cd frontend
          npm ci
          npm run build

      - name: Deploy to Vercel
        uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          working-directory: ./frontend
          vercel-args: '--prod'

# Note: Railway deploys automatically via its own GitHub integration.
# No extra job needed for the backend.
```

**GitHub Secrets to configure** (repo → Settings → Secrets → Actions):

| Secret | Where to get it |
|---|---|
| `VERCEL_TOKEN` | Vercel → Account Settings → Tokens |
| `VERCEL_ORG_ID` | Run `vercel link` in `/frontend`, check `.vercel/project.json` |
| `VERCEL_PROJECT_ID` | Same file |

---

## 11. Post-Deployment Checklist

### Backend (Railway)
- [ ] `GET /health` returns `200 OK`
- [ ] `POST /api/run` returns a `job_id`
- [ ] `GET /api/status/{job_id}` transitions correctly: `pending → running → done`
- [ ] `GET /api/results` returns `OpportunityArea[]` after a completed run
- [ ] `GET /api/signals` returns `Signal[]` records
- [ ] Railway Volume persists data after a service restart
- [ ] All API secrets (`REDDIT_CLIENT_ID`, `TWITTER_BEARER_TOKEN`, etc.) are set and valid
- [ ] Logs visible in Railway dashboard → Deployments → View Logs

### Frontend (Vercel)
- [ ] Dashboard loads at Vercel URL without errors
- [ ] "Run Pipeline" button fires `POST /api/run` (verify in browser network tab)
- [ ] Job status badge polls and transitions to `done`
- [ ] Ranked opportunity cards render with score bars
- [ ] Clicking a card opens the detail view with verbatim quotes and source links
- [ ] Signal explorer table loads and dimension/source filters work
- [ ] `NEXT_PUBLIC_API_URL` is pointing to Railway (not localhost) in production

### CORS
- [ ] Vercel origin is in the Railway `CORSMiddleware` `allow_origins` list
- [ ] No CORS errors in browser console on any API call

---

## 12. Cost Estimate

| Service | Plan | Estimated Cost |
|---|---|---|
| **Railway** | Hobby ($5/month credit included) | ~$0–$5 / month |
| **Vercel** | Hobby (free tier) | $0 |
| **Reddit API** | Free tier | $0 |
| **YouTube Data API** | Free (10,000 units/day) | $0 |
| **Twitter/X API** | Free tier (limited reads) | $0 |
| **Total** | | **~$0–$5 / month** |

> [!TIP]
> Railway's Hobby plan includes $5/month of compute credit. The FastAPI server plus infrequent pipeline runs will comfortably stay within that for a graduation project workload.

---

## Implementation Order

```
Week 1 — Backend
  ├── Build api/main.py + api/routes/pipeline.py + api/routes/results.py
  ├── Add Procfile, railway.json, runtime.txt
  ├── Patch run_pipeline.py to use ENGINE_DATA_DIR env var
  ├── Deploy to Railway, verify /health and POST /api/run
  └── Attach Railway Volume, confirm data persists

Week 2 — Frontend
  ├── Scaffold Next.js app in /frontend
  ├── Build Dashboard page + OpportunityCard + ScoreBar components
  ├── Build Opportunity Detail page with evidence quotes
  ├── Build Signal Explorer page
  └── Deploy to Vercel, connect to Railway URL

Week 3 — Polish & CI/CD
  ├── Set up .github/workflows/deploy.yml
  ├── Configure CORS properly for Vercel domain
  ├── End-to-end test (trigger → results → UI renders correctly)
  └── Final checklist sign-off
```

---

*Scoped to the `Ansh-Yadav1605/Public-Conversation-Analysis-Engine` repository
and its three-stage Python pipeline (scrape → extract → analyze → export).*
