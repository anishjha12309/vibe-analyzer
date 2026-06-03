# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Vibe Analyzer** — analyzes YouTube videos to determine their "vibe" and recommends matching Spotify tracks. Frontend (React/Vite) deploys to Vercel; backend (FastAPI) deploys to Render.com.

## Commands

### Frontend (`frontend/`)

```bash
npm run dev       # Dev server on port 5173 (proxies /api → localhost:8000)
npm run build     # tsc && vite build → dist/
npm run preview   # Preview production build
```

No lint or test scripts are configured in the frontend.

### Backend (`backend/`)

The backend uses `uv` (Rust-based Python package manager) instead of pip.

```bash
uv sync                                               # Install dependencies from lockfile
uv run uvicorn main:app --reload                      # Dev server on port 8000
uv run uvicorn main:app --host 0.0.0.0 --port $PORT  # Production start command
uv run pytest                                         # Run tests
```

### Environment Variables

**Frontend** — create `frontend/.env`:
```
VITE_API_URL=     # Leave empty for Vite dev proxy; set to backend URL for production
```

**Backend** — create `backend/.env`:
```
YOUTUBE_API_KEY=          # Google Cloud Console → YouTube Data API v3
SPOTIFY_CLIENT_ID=        # Spotify Developer Dashboard
SPOTIFY_CLIENT_SECRET=    # Spotify Developer Dashboard
ALLOWED_ORIGINS=          # Comma-separated CORS origins; defaults include localhost:5173 and *.vercel.app
```

## Architecture

### Frontend (`frontend/src/`)

- **`App.tsx`** — root component; owns the hero, result state, and orchestrates the full page layout
- **`api/client.ts`** — typed fetch wrappers; detects the `X-Quota-Warning` response header and surfaces quota errors to the UI
- **`components/Dashboard.tsx`** — deep-analysis panel combining comment sentiment with estimated audio features; uses Recharts via `VibeChart.tsx`
- **`components/TrackList.tsx`** — grid of matched Spotify tracks
- **`hooks/useLenis.ts`** — wraps Lenis smooth scrolling; `useScrollReveal.ts` drives scroll-triggered CSS animations
- **`types/api.ts`** — single source of truth for all request/response shapes shared with the backend
- **`utils/sentiment.ts`** — client-side comment sentiment classification and vibe-signal labeling

The Vite dev server proxies `/api/*` to `http://localhost:8000`, so no cross-origin config is needed during local development.

### Backend (`backend/main.py`, ~608 lines)

All backend logic lives in a single `main.py` file with these key layers:

**Vibe Classification Engine**
- 5 categories: `high_energy`, `relaxing`, `happy`, `melancholic`, `default`
- Classification order: `_VIBE_KEYWORDS` (title/description/tags) → `_CATEGORY_MAP` (YouTube category ID) → hash of `video_id` as deterministic fallback
- Each category in `_VIBE_TARGETS` holds 15 artist names used for Spotify search; 5 are seeded randomly by `video_id` for deterministic track sets per video

**Why artist search instead of Spotify Recommendations API?** Spotify deprecated its audio features and recommendations endpoints in November 2024. The backend uses `sp.search(q=artist, type="track")` instead.

**Caching** — custom `TTLCache` (256 slots, 5-minute TTL). Cache keys: `vibe:{video_id}`, `comments:{video_id}`, `features:{track_id}:{vibe}`.

**Rate Limiting** — `RollingWindowLimiter`: 5 req/min per IP for `/api/vibe-matcher`, 10 req/min for YouTube/Spotify endpoints. Returns HTTP 429.

**Quota Resilience** — YouTube quota exhaustion is caught and returns mock data with an `X-Quota-Warning` response header. Comment-disabled videos also fall back gracefully.

**Spam Filter** — `_is_spam_track()` rejects compilation artists and suspiciously long track names from Spotify results.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/vibe-matcher` | Main endpoint: accepts `youtube_url` or `video_id`, returns tracks + vibe label |
| GET | `/api/youtube/comments/{video_id}` | Top 50 comments (relevance-sorted) |
| GET | `/api/spotify/track-features/{track_id}?vibe=<key>` | Estimated audio features for vibe profile |
| GET | `/health` | `{status, cache_size}` |

### Deployment

- Frontend → Vercel (`vercel.json`): SPA rewrites all routes to `index.html`
- Backend → Render.com (`render.yaml`): build with `pip install uv && uv sync --frozen`, start with `uv run uvicorn main:app`
