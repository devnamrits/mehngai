# Deploying Mehngai — free tier, ~15 minutes

All three services log in with your **GitHub account** (no cards).

## 1. Database — Neon (free Postgres)
1. https://neon.com → **Sign up with GitHub**
2. Create project `mehngai` → copy the **connection string** (looks like `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`)
3. Keep this tab open — this is your `DATABASE_URL`

## 2. Backend — Render (free web service)
1. https://render.com → **Sign in with GitHub** → authorize repo access
2. **New → Blueprint** → select `devnamrits/mehngai` → Render reads `backend/render.yaml`
3. Before Create, fill the `sync: false` env vars:
   - `DATABASE_URL` → paste Neon connection string
   - `BRIGHTDATA_API_KEY` → your key
   - `COLLECTOR_IDS` → `c_mt5c5hypmg1k6ihr,c_mt5c5gb22ixnkdfvp7,c_mt5c5en7o0dctyrts,c_mt5m7lfd1bzykx33up`
   - `CORS_ORIGINS` → `https://<your-app>.vercel.app` (fill after step 3, edit later)
4. Create → wait for build → note your URL: `https://mehngai-api.onrender.com`
5. Verify: `curl https://mehngai-api.onrender.com/api/v1/health`

## 3. Frontend — Vercel (free)
1. https://vercel.com → **Continue with GitHub** → Import `devnamrits/mehngai`
2. Root Directory: `frontend` · Framework: Next.js (auto)
3. Env var: `NEXT_PUBLIC_API_URL` = `https://mehngai-api.onrender.com`
4. Deploy → note your URL

## 4. Weekly scan — GitHub Actions
Repo → Settings → Secrets → Actions → New:
- `MEHNGAI_API_URL` = your Render URL
- `PIPELINE_TOKEN` = value from backend `.env` / Render env
The workflow (`weekly.yml`) fires Mondays 03:00 IST and also wakes the sleeping free instance.

## Local development
```bash
./dev-up.sh        # starts API :8000 + UI :3000 with local .env files
```
