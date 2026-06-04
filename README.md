# Vibe Analyzer

> Drop a YouTube link. Get the vibe. Discover matching music.

Vibe Analyzer extracts the mood of any YouTube video — from its title, tags, category, and comment sentiment — then surfaces a curated set of Spotify tracks that match that energy.

---

## Features

- **Vibe Classification** — 5 categories (High Energy, Chill & Relaxing, Happy & Uplifting, Melancholic, Balanced) derived from keyword matching, YouTube category IDs, and a deterministic hash fallback
- **Spotify Track Matching** — up to 20 curated tracks per vibe via artist search (Spotify deprecated its Recommendations API in Nov 2024)
- **Comment Sentiment Analysis** — keyword-based positive/neutral/negative classification with breakdown percentages
- **Audio Feature Profiles** — vibe-estimated Spotify audio attributes (valence, energy, danceability, tempo, acousticness, and more) per track
- **Smart Caching** — in-memory TTL cache (256 slots, 5-minute expiry) for vibe matches, comments, and features
- **Rate Limiting** — rolling-window limiter: 5 req/min on the main endpoint, 10 req/min on YouTube/Spotify passthrough endpoints
- **Quota Resilience** — graceful fallback to mock data with an `X-Quota-Warning` header when YouTube quota is exhausted or comments are disabled
- **Premium UI** — Lenis smooth scroll, scroll-reveal animations, responsive bento grid, vibe-colored badges

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript 5, Vite 5 |
| Charts | Recharts 2 |
| Smooth Scroll | Lenis 1.3 |
| Fonts | Plus Jakarta Sans (self-hosted variable font) |
| Backend | FastAPI, Python ≥ 3.11, Uvicorn |
| Data | YouTube Data API v3, Spotify Web API (Spotipy) |
| Validation | Pydantic v2 |
| Package Manager | `uv` (Rust-based Python manager) |
| Frontend Deploy | Vercel |
| Backend Deploy | Render.com |

---

## Project Structure

```
byte/
├── frontend/               # React / Vite SPA
│   ├── src/
│   │   ├── api/client.ts        # Typed fetch wrappers; quota-warning detection
│   │   ├── components/
│   │   │   ├── Dashboard.tsx    # Sentiment + audio features analysis panel
│   │   │   ├── TrackList.tsx    # Spotify track grid
│   │   │   ├── VibeChart.tsx    # Recharts vibe signal comparison
│   │   │   └── VibeBadge.tsx    # Color-coded vibe label
│   │   ├── hooks/
│   │   │   ├── useLenis.ts      # Smooth scroll setup
│   │   │   ├── useScrollReveal.ts
│   │   │   ├── useCommentAnalysis.ts
│   │   │   └── useTrackFeatures.ts
│   │   ├── utils/sentiment.ts   # Client-side comment classifier
│   │   ├── types/api.ts         # Shared request/response types
│   │   └── App.tsx
│   └── vercel.json
└── backend/
    ├── main.py             # All backend logic (~757 lines)
    ├── pyproject.toml
    └── render.yaml
```

---

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) — `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- YouTube Data API v3 key ([Google Cloud Console](https://console.cloud.google.com/))
- Spotify app credentials ([Spotify Developer Dashboard](https://developer.spotify.com/dashboard))

### 1. Clone

```bash
git clone https://github.com/Anish-byte/byte.git
cd byte
```

### 2. Backend

```bash
cd backend
cp .env.example .env        # then fill in your keys
uv sync
uv run uvicorn main:app --reload
# → http://localhost:8000
```

**`backend/.env`**
```env
YOUTUBE_API_KEY=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
ALLOWED_ORIGINS=            # comma-separated; defaults include localhost:5173 and *.vercel.app
```

### 3. Frontend

```bash
cd frontend
cp .env.example .env        # leave VITE_API_URL empty for the dev proxy
npm install
npm run dev
# → http://localhost:5173
```

The Vite dev server proxies `/api/*` → `http://localhost:8000`, so no CORS config is needed locally.

---

## API Reference

### `POST /api/vibe-matcher`

Accepts a YouTube URL or raw video ID and returns the vibe classification with matching tracks.

**Request**
```json
{ "youtube_url": "https://www.youtube.com/watch?v=..." }
```

**Response**
```json
{
  "video": {
    "video_id": "dQw4w9WgXcQ",
    "title": "...",
    "description": "...",
    "tags": ["..."],
    "category_id": "10",
    "view_count": 1500000000,
    "like_count": 15000000,
    "vibe_profile": "high_energy"
  },
  "tracks": [
    {
      "id": "...",
      "name": "...",
      "artists": ["..."],
      "album": "...",
      "preview_url": "...",
      "external_url": "..."
    }
  ],
  "vibe_label": "High Energy",
  "audio_profile": {
    "danceability": 0.82,
    "energy": 0.91,
    "valence": 0.74,
    "tempo": 128.0,
    "acousticness": 0.05,
    "instrumentalness": 0.12,
    "speechiness": 0.08,
    "loudness": -4.2
  }
}
```

Rate limit: **5 req/min per IP**. Quota warnings returned via `X-Quota-Warning` header.

---

### `GET /api/youtube/comments/{video_id}`

Returns up to 50 relevance-sorted comments. Falls back gracefully if comments are disabled or the YouTube quota is exhausted.

| Query param | Default | Description |
|---|---|---|
| `limit` | `50` | Max comments to return |

---

### `GET /api/spotify/track-features/{track_id}`

Returns vibe-estimated Spotify audio features for a given track.

| Query param | Values |
|---|---|
| `vibe` | `high_energy` · `relaxing` · `happy` · `melancholic` · `default` |

---

### `GET /health`

```json
{ "status": "ok", "cache_size": 45 }
```

---

## Vibe Categories

| Vibe | Characteristics | Example Content |
|---|---|---|
| **High Energy** | BPM 128+, high energy & danceability | EDM, gaming, workout |
| **Chill & Relaxing** | Low tempo, high acousticness | Lo-fi, ambient, nature |
| **Happy & Uplifting** | High valence, moderate energy | Pop, feel-good vlogs |
| **Melancholic** | Low valence, mid-low energy | Indie, alternative, ballads |
| **Balanced** | Mid-range all features | Mixed or uncategorized content |

Classification order: keyword matching in title/description/tags → YouTube category ID mapping → deterministic MD5 hash of `video_id` as fallback (same video always resolves to the same vibe).

---

## Deployment

### Frontend → Vercel

Push to your connected GitHub repo. `vercel.json` handles the SPA rewrite (`/* → /index.html`) and sets the output directory to `dist`.

Set `VITE_API_URL` in Vercel's environment variables to your Render backend URL.

### Backend → Render.com

`render.yaml` is pre-configured:

```yaml
buildCommand: pip install uv && uv sync --frozen
startCommand:  uv run uvicorn main:app --host 0.0.0.0 --port $PORT
```

Add these environment variables in the Render dashboard:

```
YOUTUBE_API_KEY
SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET
ALLOWED_ORIGINS      # e.g. https://your-app.vercel.app
```

---

## Architecture Notes

- **Single-file backend** — all logic lives in `main.py` for simplicity and easy audit; split by layer if the project grows
- **Artist search over Recommendations API** — Spotify deprecated audio features and recommendations endpoints in November 2024; the backend searches by curated artist name instead
- **Deterministic track sets** — `video_id` seeds both vibe assignment and the random artist selection so the same video always returns the same tracks
- **Client-side sentiment** — a simple keyword classifier in `utils/sentiment.ts` keeps the comment analysis fast and dependency-free
- **In-memory TTL cache** — sufficient for this scale; no Redis dependency required

---

## License

MIT
