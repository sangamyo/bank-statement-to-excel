# Bank Statement to Excel

**Live demo:** https://bank-statement-to-excel-virid.vercel.app

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sangamyo/bank-statement-to-excel)

The backend deploys to Render from [`render.yaml`](render.yaml), and the frontend is on Vercel. On Render's free plan the API sleeps when idle, so the first request after a while can take about 50 seconds.


Convert bank statement PDFs into clean, styled Excel workbooks.

Upload a text-based statement PDF. The backend rebuilds the transaction table from the positions of the words on each page, so it doesn't depend on table borders. It merges multi-line narrations, normalises dates and amounts, checks that the running balance adds up, and returns an `.xlsx` with three sheets:

| Sheet | Contents |
|---|---|
| **Transactions** | One row per transaction, with the statement's own column names and order |
| **Summary** | Bank, transaction count, total debit/credit, opening/closing balance, date range, number of balance-continuity errors |
| **Raw Text** | The raw text lines of the PDF, for auditing |

The frontend is a small dashboard with Dashboard, Convert, History and Settings pages. It covers uploading, polling progress, downloading, deleting, and per-browser history.

## Supported banks

The parser works from the column layout, so it isn't tied to a single bank's template. It has been tested on statements from:

- **HDFC Bank**, **ICICI Bank**, **State Bank of India**, **Kotak Mahindra Bank**
- **Axis Bank** (single `Amount` column plus a `DR/CR` column)
- **Punjab National Bank**, and other Indian banks with the usual
  `Date / Narration / Ref / Withdrawal / Deposit / Balance` layouts

The bank is identified from the IFSC code or the bank name in the statement header. Unknown banks still go through the generic parser.

**Limitations:** scanned or image-only PDFs need OCR, which isn't included. Password-protected PDFs must be unlocked first. Layouts where the amount column has no header can't be mapped automatically.

## Stack

| Part | Tech |
|---|---|
| Frontend | React 18, Vite 6, Tailwind CSS 4, shadcn/ui (Radix), React Router 7 |
| Backend | Python 3.13, FastAPI, pdfplumber, pandas, openpyxl, SQLite |
| Optional | Camelot + OpenCV, used as a table-extraction fallback (`requirements-extra.txt`) |

```
.
├── frontend/              React app (deploy to Vercel)
│   ├── src/app/pages/     Dashboard, ConvertPDF, History, Settings
│   ├── src/app/services/api.ts
│   └── vercel.json        SPA rewrite
└── backend/               FastAPI app (deploy to Railway)
    ├── app.py             ASGI entrypoint, CORS, retention task
    ├── config.py          Environment configuration
    ├── routes/            /api/upload, /api/download, /api/history, /api/stats
    ├── services/          Pipeline: clean → merge → validate → Excel
    ├── parsers/           Spatial table parser + fallback
    ├── database/          SQLite history
    ├── tests/
    └── Dockerfile
```

### API

All endpoints are under `/api`. Send an `X-Client-Id` header (any random 8–64 character id) to scope history to one browser. The frontend generates the id and keeps it in `localStorage`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/upload` | multipart `file` (PDF). Returns `{message, file: {id, fileName, date, status, fileSize}}`. Conversion runs in the background |
| `GET` | `/api/history` | This client's conversions |
| `GET` | `/api/history/{id}` | One conversion (used for status polling) |
| `DELETE` | `/api/history/{id}` | Delete the record **and** its files |
| `GET` | `/api/download/{id}` | Download the `.xlsx` (404 for other clients' files) |
| `GET` | `/api/stats` | Dashboard counters for this client |
| `GET` | `/api/health` | Health check, plus `max_upload_mb` and `retention_hours` |

## Local setup

Requirements: Python 3.10+ (tested on 3.13) and Node 18+.

```bash
# Backend: http://localhost:8000
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # or requirements-extra.txt for the Camelot fallback
uvicorn app:app --reload --port 8000     # add --env-file .env to load settings from a file

# Frontend: http://localhost:5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Run the tests:

```bash
cd backend && python tests/test_pipeline.py      # or: pytest tests
```

## Environment variables

### Backend (`backend/.env.example`)

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Set to `production` to stop allowing localhost CORS origins and disable auto-reload |
| `ALLOWED_ORIGINS` | *(empty)* | Comma-separated frontend origins, e.g. `https://your-app.vercel.app`. Outside production, `localhost:5173/4173/3000` are always allowed |
| `ALLOWED_ORIGIN_REGEX` | *(unset)* | Optional origin regex, e.g. for Vercel preview URLs |
| `DATA_DIR` | `backend/data` | Root for `uploads/`, `outputs/` and `history.db`. Created automatically |
| `MAX_UPLOAD_MB` | `10` | Upload size limit. Larger files get HTTP 413 |
| `RETENTION_HOURS` | `24` | Converted files and history older than this are deleted. `0` disables cleanup |
| `CLEANUP_INTERVAL_MINUTES` | `15` | How often the retention cleanup runs |
| `PORT` | `8000` | Listen port (Railway sets this automatically) |

### Frontend (`frontend/.env.example`)

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `/api` | Full backend API URL including `/api`, e.g. `https://your-api.up.railway.app/api`. Read at build time |
| `VITE_DEV_PROXY_TARGET` | `http://localhost:8000` | Dev only: where `npm run dev` proxies `/api` |

## Deploy

### Backend on Railway

1. Create a new project from this GitHub repo.
2. Service settings: set **Root Directory** to `backend`. Railway detects the `Dockerfile` (`python:3.13-slim`) and starts `uvicorn` on `$PORT`.
3. Add a **Volume** mounted at `/data`. The image already sets `DATA_DIR=/data`, so history and generated files survive redeploys.
4. Variables: `APP_ENV=production`, `ALLOWED_ORIGINS=https://<your-app>.vercel.app`, and optionally `RETENTION_HOURS` and `MAX_UPLOAD_MB`.
5. Set the health check path to `/api/health`.

To include the optional Camelot/OpenCV fallback, add the build argument `INSTALL_EXTRAS=true`. It roughly doubles the image size.

### Frontend on Vercel

1. Import the repo and set **Root Directory** to `frontend`. The framework preset is **Vite**: build `npm run build`, output `dist`.
2. Set the environment variable `VITE_API_URL=https://<your-backend>.up.railway.app/api`.
3. `frontend/vercel.json` rewrites every route to `index.html`, so deep links like `/history` work.

## Privacy

Bank statements are sensitive, so this demo is built to keep as little as possible:

- **Uploaded PDFs are deleted** as soon as conversion finishes, whether it succeeds or fails.
- **Excel files and history entries expire** after `RETENTION_HOURS` (24 h by default). A background task deletes them, along with any orphaned files.
- **Deleting a history entry** removes its Excel file from the server immediately. Settings also has a "Delete all my conversions" button.
- **Per-browser isolation:** history, stats, downloads and deletes are scoped to an anonymous `X-Client-Id` stored in the browser. Other visitors get 404 for your files. This isn't authentication: anyone holding your id could see your files until they expire. Don't use a public instance for statements you can't afford to expose; self-host instead.
- Files are stored under random UUID names. Statement contents and balances are never written to the logs.
- **This repository contains no real statements.** `.gitignore` excludes `*.pdf`, `*.xlsx`, `*.db`, `*.log`, `data/`, `uploads/` and `outputs/`. Keep test statements out of the repo.

## Credits

UI components from [shadcn/ui](https://ui.shadcn.com/) (MIT). See `frontend/ATTRIBUTIONS.md`.
