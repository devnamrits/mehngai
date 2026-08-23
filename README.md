# Mehngai 📈

> A live, independent cost-of-living index — computed daily from real shelf prices by **self-healing web scrapers** that never go down.
>
> *Into the Scrape-Verse* hackathon submission · WeMakeDevs × Bright Data · Aug 2026

Official inflation stats lag weeks and measure baskets nobody buys. Mehngai reads regional supermarket catalog pages daily through Bright Data Scraper Studio collectors, normalizes everything into comparable ₹/kg·₹/L unit prices, chains them into a transparent index — and when a retail site changes its layout at 2am, the built-in watchdog detects the drift and heals the collector autonomously. Same Collector ID, zero downtime, receipts logged.

## Architecture

Editable HLD: [`docs/HLD.md`](docs/HLD.md) · TS reference prototype: [`prototype/`](prototype)

```mermaid
flowchart LR
    U[User] --> FE["Next.js dashboard<br/>(Vercel)"]
    CRON["GitHub Actions<br/>cron"] -->|"POST /pipeline/run"| BE["FastAPI backend<br/>(Render)"]
    FE <-->|"REST + SSE pulse"| BE
    BE --> PG[("Neon Postgres")]
    BE -->|"/dca trigger · poll · heal"| BD["Bright Data<br/>Scraper Studio"]
    BD --> SITES[(Supermarket<br/>public pages)]
```

### The self-healing loop (the heart of this project)

```mermaid
sequenceDiagram
    participant ORC as OrchestratorService
    participant VAL as DriftValidators
    participant BD as Bright Data API
    participant DB as Postgres
    loop each collector c_*
        ORC->>BD: POST /dca/trigger
        BD-->>ORC: rows[]
        ORC->>VAL: verdicts(rows)
        alt critical drift detected
            VAL-->>ORC: empty_run / schema_drift / null_ratio / price_outlier
            ORC->>DB: open incident + pulse event
            ORC->>BD: refactor_template -> progress -> approve
            Note over BD: plain-language heal prompt,<br/>same Collector ID preserved
            ORC->>BD: re-trigger
            ORC->>DB: ingest healed rows (status=healed)
        else healthy
            ORC->>DB: ingest rows
        end
    end
    ORC->>DB: upsert chained index points
```

## AI component

`GET /api/v1/insights/daily` produces a plain-language daily briefing from verified data facts. Point `AI_BASE_URL` at any OpenAI-compatible endpoint — **Ollama locally** (`http://localhost:11434/v1`), or a DGX Spark later — for LLM narration; without it, a deterministic template briefing is served so the feature never breaks and costs nothing.

## Monorepo layout

```
├── docs/               HLD + diagrams (mermaid, renders on GitHub)
├── backend/            FastAPI · SQLAlchemy · hexagonal ports/adapters · pytest (11 tests)
│   ├── app/{core,domain,ports,adapters,services,api}
│   ├── scripts/seed_mock.py   # 14-day history backfill, zero credits
│   ├── tests/          validators · normalizer · index math · heal-flow orchestration
│   └── render.yaml     # one-click Render deploy
├── frontend/           Next.js editorial dashboard (Vercel) — in progress
└── prototype/          TypeScript reference implementation kept for provenance
```

## Run it locally (mock mode — no Bright Data account needed)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # COLLECTOR_IDS=mock-chain-a,mock-chain-b,mock-chain-c
python -m scripts.seed_mock --days 14
uvicorn app.main:app --reload
```

Then:

```bash
curl localhost:8000/api/v1/index                       # chained index series
curl "localhost:8000/api/v1/prices?q=milk"             # cross-chain price grid
curl localhost:8000/api/v1/movers?window_days=7        # wall of movers
curl localhost:8000/api/v1/insights/daily              # AI briefing
curl -X POST -H "Authorization: Bearer devtoken" \
     localhost:8000/api/v1/pipeline/run                # nightly run (mock scraper)

# watch the self-healing loop live:
MOCK_FAIL_COLLECTOR=mock-chain-b uvicorn app.main:app --port 8001
# then run the pipeline again -> drift -> auto-heal -> status=healed
```

## Switching to real Bright Data collectors

```bash
npx -p @brightdata/cli bdata scraper create <catalog-url> "Extract product title, price, pack size"
export BRIGHTDATA_API_KEY=...      # headless auth, no bdata login needed
COLLECTOR_IDS=c_aaa,c_bbb,c_ccc    # pin real IDs; MOCK_MODE off automatically
```

## How Bright Data Scraper Studio powers Mehngai

Scraper Studio is not an add-on here — **every data point in the product originates from a custom Studio collector**:

1. **Creation** — each tracked chain has a collector built with `bdata scraper create <category-url> "<field description>"`. The AI Agent generates the output schema (`title, price, pack_size, brand, url`), writes the scraper code, and returns a `c_*` Collector ID. We run Discovery-type collectors over public category/listing pages of regional Indian grocery chains.
2. **Running** — collectors are production APIs: our backend triggers them via `POST /dca/trigger`, polls `GET /dca/dataset/{id}`, and ingests rows. No scraping servers of our own — proxies, retries and unblocking are Bright Data's.
3. **Self-healing** — our watchdog validates every run (empty-run / null-ratio / schema-drift / price-outlier heuristics). On critical drift it calls the native heal flow (`refactor_template → progress → resume_automation_job`) with a field-level plain-language prompt. The Collector ID never changes, so nothing downstream is reconfigured. First heal per collector is supervised; afterwards healing is autonomous, with every incident receipted in `incidents`.
4. **Why these targets** — all chains are public catalog pages without login or paywall; none are covered by Bright Data's pre-built scraper library; no government websites are touched.

## Deployment

| Piece | Host | Notes |
|---|---|---|
| `backend/` | Render free web service | `render.yaml` included; set env vars from `backend/.env.example` |
| Database | Neon free Postgres | connection string goes in `DATABASE_URL`; survives restarts |
| `frontend/` | Vercel free | Next.js; set `NEXT_PUBLIC_API_URL` to your Render URL |
| Scheduler | GitHub Actions | `nightly.yml` cron POSTs `/pipeline/run`; set repo secrets `MEHNGAI_API_URL`, `PIPELINE_TOKEN` |

## AI assistance disclosure

This project was built with AI coding assistance (Claude Code) for scaffolding, boilerplate, and iteration speed. All architecture decisions, target selection, compliance checks, and code review were performed by the team, who can explain every module — see `docs/HLD.md`, `docs/PRODUCT.md`, and the test suite for the reasoning trail.

## Compliance

Public catalog pages only · no login/paywall/personal data · no government sites · custom Scraper Studio collectors (not library) · secrets via env only · AI assistance disclosed above.
