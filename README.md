# Smart Inbox MVP

This repository contains a runnable MVP for a smart inbox web app that supports Gmail OAuth, inbox ranking, and a feedback loop.

- Frontend: React + Vite + TypeScript
- Backend: FastAPI + SQLAlchemy + SQLite (development)
- Core product features:
  - Inbox buckets: `Now / Read / Skim / Later`
  - Busy/Normal reading mode
  - Priority scoring and bucketing
  - Feedback loop (`important`, `not_important`, `mute_sender`, `remind_sender`)
  - Interaction event tracking
  - Gmail OAuth + real inbox sync (for connected users)

---

## 1) Project Structure and Responsibilities

```text
backend/
  app/
    api/
      routes.py          # All HTTP endpoints (where to add new APIs)
    core/
      config.py          # Env loading and app config
    services/
      auth.py            # OAuth and token refresh
      gmail_sync.py      # Gmail API sync and parsing
      ranking.py         # Priority scoring rules (adaptive logic entry)
      summary.py         # Busy mode summary generation
      sync.py            # Demo sync fallback
    db.py                # SQLAlchemy session/base
    models.py            # DB models
    schemas.py           # Pydantic request/response schemas
    main.py              # FastAPI app bootstrap
  requirements.txt
  .env.example

frontend/
  src/
    components/          # Reusable UI blocks
    api.ts               # Frontend -> backend API calls
    types.ts             # Frontend types
    App.tsx              # Main page orchestration and app flow
    styles.css           # Base styling
```

---

## 2) Quick Start

### Option A: One-command startup

From repo root:

```powershell
.\start.ps1
```

If dependencies are already installed:

```powershell
.\start.ps1 -SkipInstall
```

### Option B: Start manually

#### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

- `http://localhost:5173/` (recommended)

---

## 3) Gmail OAuth Setup

1. Go to Google Cloud Console -> `APIs & Services`.
2. Enable `Gmail API` for your project.
3. Create OAuth Client (`Web application`).
4. Configure redirect URI:
   - `http://127.0.0.1:8000/api/auth/google/callback`
5. Configure consent screen (External), scopes, and test users.

Create local env file:

```bash
cd backend
copy .env.example .env
```

Set values in `backend/.env`:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `FRONTEND_OAUTH_DONE_URI`

Debug config status:

- `GET /api/auth/debug-config`

---

## 4) Existing API Endpoints

- `GET /api/auth/google/start` -> get Google OAuth URL
- `GET /api/auth/google/callback` -> OAuth callback
- `GET /api/auth/complete` -> OAuth bridge page
- `GET /api/auth/status` -> check current auth status
- `GET /api/auth/debug-config` -> check auth config loaded
- `POST /api/sync/run` -> sync inbox (Gmail if connected, demo otherwise)
- `GET /api/inbox?bucket=now|read|skim|later`
- `GET /api/emails/{id}?mode=busy|normal`
- `POST /api/emails/{id}/feedback`
- `POST /api/events`

---

## 5) Where to Add New Backend APIs

When you want to add new APIs, follow this order:

1. Add request/response models in `backend/app/schemas.py`.
2. Add or extend DB models in `backend/app/models.py` (if new data is needed).
3. Add business logic in `backend/app/services/*.py` (preferred, keep routes thin).
4. Register endpoint in `backend/app/api/routes.py`.
5. If config/env needed, add in `backend/app/core/config.py` + `.env.example`.

Example use cases:

- Add "notification digest API":
  - business logic -> `services/notification.py`
  - endpoint -> `routes.py`
  - response schema -> `schemas.py`

- Add "thread importance API":
  - thread stats model -> `models.py`
  - scoring logic -> `services/ranking.py`
  - endpoint -> `routes.py`

---

## 6) Where to Add Frontend Features

Main extension points:

- API calls: `frontend/src/api.ts`
- App-level state and flow: `frontend/src/App.tsx`
- Reusable UI components: `frontend/src/components/*`
- Type definitions: `frontend/src/types.ts`
- Styles: `frontend/src/styles.css`

Typical workflow for a new UI feature:

1. Add backend endpoint.
2. Add function in `api.ts`.
3. Add/extend types in `types.ts`.
4. Add component in `components/`.
5. Integrate component and state in `App.tsx`.

---

## 7) Where to Add Adaptive Logic (Most Important)

Current scoring is rule-based and lives in:

- `backend/app/services/ranking.py`

Current feedback/event ingestion lives in:

- `POST /api/emails/{id}/feedback` in `backend/app/api/routes.py`
- `POST /api/events` in `backend/app/api/routes.py`

### Recommended adaptive architecture

1. **Feature extraction layer**
   - Keep in `services/ranking.py`
   - Build feature vector per email (sender, is_cc, attachment, action keyword, length, thread activity, etc.)

2. **User preference / stats storage**
   - Extend `models.py`
   - Add sender/thread/feature statistics tables (or JSON columns for MVP)

3. **Online update logic**
   - Add helper module, e.g. `services/adaptation.py`
   - Update user stats/weights when feedback/events arrive
   - Trigger from `routes.py` after storing interaction events

4. **Scoring integration**
   - `score_email()` should read updated user stats
   - Recompute score + bucket on sync and on interaction updates

### Practical implementation order

1. Add sender-level stats model (`open_count`, `reply_count`, `skip_count`).
2. Update sender stats in `/events` and `/feedback`.
3. Inject sender bias into `score_email`.
4. Add feature weights per user and online update rule.
5. Add scheduled decay to avoid stale behavior locking.

---

## 8) Data and Runtime Notes

- Gmail-connected users use real Gmail sync in `services/gmail_sync.py`.
- Without Gmail auth header, system uses demo sync in `services/sync.py`.
- Access token auto-refresh is implemented in `services/auth.py`.
- Busy mode summary is currently heuristic in `services/summary.py` and can be replaced with LLM calls.

---

## 9) Troubleshooting

- `redirect_uri_mismatch`:
  - Ensure Google Console redirect URI exactly matches `GOOGLE_REDIRECT_URI`.
- OAuth start returns config error:
  - Verify `.env` loaded via `GET /api/auth/debug-config`.
- Gmail 403 `accessNotConfigured`:
  - Enable `gmail.googleapis.com` in Google Cloud project.
- Frontend OAuth callback fails:
  - Ensure frontend is running and `FRONTEND_OAUTH_DONE_URI` matches active frontend host.
