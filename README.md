# Global Signal Map

## Structure

- `frontend/`: UI files (`index.html`, `styles.css`, `script.js`)
- `backend/`: FastAPI server, routes, services, config
- `docs/`: active project documents
- `archive/legacy-root-docs/`: previous root-level document snapshots

## Server

- Entry point: `main.py`
- FastAPI app: `backend/main.py`
- Static frontend is served from `frontend/`
- News APIs:
  - `GET /api/news/home`
  - `GET /api/news/category/{category}`
- Market APIs:
  - `GET /api/market/gold`
  - `GET /api/market/wti`
  - `GET /api/market/sp500`
  - Legacy `GET /api/market/economy` has been removed

## Environment

Use `.env.example` as the base.

Required keys:

- `MONGODB_URI` or `MONGODB_URL`
- `MONGODB_DB_NAME`
- `NEWSAPI_API_KEY`
- `OPENAI_API_KEY` (optional, for higher-quality Korean translation)

## Market Data

- Gold: `GC=F`
- WTI Oil: `CL=F`
- S&P 500: `^GSPC`
- Source: `yfinance` / Yahoo Finance
- API key: not required

## Install

```powershell
python -m pip install -r requirements-server.txt
```

## Run Local

```powershell
uvicorn main:app --reload --port 8000
```

## Docker Run

```powershell
docker build -t global-issue-map .
docker run --env-file .env -p 8000:8000 global-issue-map
```

## Vercel Deploy

1. Push this project to GitHub
2. Import the repo in Vercel
3. Set these environment variables in Vercel Project Settings
   - `MONGODB_URI` or `MONGODB_URL`
   - `MONGODB_DB_NAME`
   - `NEWSAPI_API_KEY`
   - `OPENAI_API_KEY` (optional)
   - `OPENAI_MODEL` (optional)
   - `SESSION_COOKIE_NAME`
4. Deploy with the included `app.py`, `vercel.json`, `requirements.txt`, and `public/` assets

Notes:
- `public/` serves the static frontend on Vercel
- `app.py` is the FastAPI entrypoint for Vercel Python runtime
- `requirements.txt` is the slim production dependency set for Vercel

## Deploy

Any Linux host that supports Docker or a Python web service can run this app.

Recommended deployment shape:

1. Add the environment variables from `.env.example`
2. Set the start command to `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Ensure outbound HTTPS access is allowed to:
   - `newsapi.org`
   - Yahoo Finance endpoints used by `yfinance`
   - `api.openai.com` (optional)

## Health Check

- `GET /api/health`
- `GET /info`

## Notes

- MongoDB connection is handled in `backend/main.py`
- Market service lives in `backend/services/market_service.py`
- Market router lives in `backend/routes/market_router.py`
- If outbound network is blocked, market endpoints return `503` with a connection-blocked message
