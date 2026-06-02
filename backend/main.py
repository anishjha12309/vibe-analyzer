from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any

import spotipy
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from googleapiclient.discovery import build
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from spotipy.oauth2 import SpotifyClientCredentials


# ─── Config ────────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    youtube_api_key: str
    spotify_client_id: str
    spotify_client_secret: str
    allowed_origins: str = "http://localhost:5173,https://*.vercel.app"

    class Config:
        env_file = ".env"


settings = Settings()


# ─── LRU TTL Cache (5-minute TTL) ──────────────────────────────────────────────

class TTLCache:
    def __init__(self, maxsize: int = 256, ttl: int = 300):
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str) -> tuple[bool, Any]:
        if key not in self._store:
            return False, None
        value, ts = self._store[key]
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return False, None
        self._store.move_to_end(key)
        return True, value

    def set(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, time.monotonic())
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)


_cache = TTLCache()


# ─── Rolling-Window Rate Limiter ────────────────────────────────────────────────

class RollingWindowLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, dict[str, list[float]]] = {}

    def is_allowed(self, ip: str, group: str, max_requests: int, window: int = 60) -> bool:
        now = time.monotonic()
        self._windows.setdefault(ip, {}).setdefault(group, [])
        ts_list = self._windows[ip][group]
        self._windows[ip][group] = [t for t in ts_list if now - t < window]
        if len(self._windows[ip][group]) >= max_requests:
            return False
        self._windows[ip][group].append(now)
        return True


_limiter = RollingWindowLimiter()
_LIMITS: dict[str, int] = {"vibe_matcher": 5, "youtube": 10, "spotify": 10}


def _check_rate(request: Request, group: str) -> None:
    ip = request.client.host if request.client else "unknown"
    if not _limiter.is_allowed(ip, group, _LIMITS.get(group, 10)):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {_LIMITS.get(group)} req/min for {group}. Try again shortly.",
        )


# ─── API Client Factories ───────────────────────────────────────────────────────

def _yt():
    return build("youtube", "v3", developerKey=settings.youtube_api_key)


def _sp() -> spotipy.Spotify:
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=settings.spotify_client_id,
            client_secret=settings.spotify_client_secret,
        )
    )


# ─── Pydantic Schemas ───────────────────────────────────────────────────────────

class VibeMatcherRequest(BaseModel):
    youtube_url: str | None = None
    video_id: str | None = None


class SpotifyTrack(BaseModel):
    id: str
    name: str
    artists: list[str]
    album: str
    preview_url: str | None = None
    external_url: str


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    description: str
    tags: list[str]
    category_id: str
    view_count: int
    like_count: int
    vibe_profile: dict[str, Any]


class VibeMatcherResponse(BaseModel):
    video: VideoMetadata
    tracks: list[SpotifyTrack]
    vibe_label: str
    audio_profile: AudioFeatures  # vibe-estimated values (Spotify audio-features deprecated Nov 2024)


class Comment(BaseModel):
    author: str
    text: str
    like_count: int
    published_at: str


class AudioFeatures(BaseModel):
    id: str
    danceability: float
    energy: float
    valence: float
    tempo: float
    acousticness: float
    instrumentalness: float
    speechiness: float
    loudness: float


# ─── Vibe Classification Engine ─────────────────────────────────────────────────

_CATEGORY_MAP: dict[str, str] = {
    "20": "gaming", "17": "sports", "10": "music",
    "26": "howto", "22": "people", "25": "news", "28": "science",
}

_VIBE_KEYWORDS: dict[str, list[str]] = {
    "high_energy": [
        "gaming", "fps", "workout", "gym", "fitness", "action", "sports",
        "race", "battle", "fight", "adrenaline", "intense", "hype",
        "edm", "dubstep", "drum and bass", "dnb", "hardstyle", "techno",
    ],
    "relaxing": [
        "lofi", "lo-fi", "chill", "relax", "sleep", "calm", "nature",
        "ambient", "cozy", "study", "peaceful", "meditation", "rain",
        "soft", "gentle", "slow", "acoustic", "jazz", "classical",
    ],
    "happy": [
        "funny", "comedy", "laugh", "happy", "joy", "celebration", "party",
        "fun", "vlog", "travel", "adventure", "positive", "wholesome",
        "dance", "pop", "summer", "upbeat", "feel good",
    ],
    "melancholic": [
        "sad", "emotional", "depression", "anxiety", "loss", "grief",
        "heartbreak", "lonely", "nostalgic", "melancholy", "bitter",
        "symphony", "orchestral", "strings", "cinematic", "indie",
        "alternative", "grunge", "dark", "reflection", "sorrow",
    ],
}

_VIBE_TARGETS: dict[str, dict[str, Any]] = {
    "high_energy": {
        "label": "High Energy",
        "search_queries": [
            "Skrillex",
            "Daft Punk",
            "The Prodigy",
            "Calvin Harris",
            "Avicii",
        ],
        "est_features": {
            "danceability": 0.82, "energy": 0.91, "valence": 0.65,
            "tempo": 138.0, "acousticness": 0.04, "instrumentalness": 0.15,
            "speechiness": 0.06, "loudness": -4.0,
        },
    },
    "relaxing": {
        "label": "Chill & Relaxing",
        "search_queries": [
            "Nils Frahm",
            "Ludovico Einaudi",
            "Olafur Arnalds",
            "Tycho",
            "Brian Eno",
        ],
        "est_features": {
            "danceability": 0.48, "energy": 0.28, "valence": 0.32,
            "tempo": 75.0, "acousticness": 0.72, "instrumentalness": 0.65,
            "speechiness": 0.03, "loudness": -12.0,
        },
    },
    "happy": {
        "label": "Happy & Uplifting",
        "search_queries": [
            "Pharrell Williams",
            "Bruno Mars",
            "Dua Lipa",
            "Harry Styles",
            "Lizzo",
        ],
        "est_features": {
            "danceability": 0.75, "energy": 0.68, "valence": 0.84,
            "tempo": 118.0, "acousticness": 0.18, "instrumentalness": 0.02,
            "speechiness": 0.07, "loudness": -5.5,
        },
    },
    "melancholic": {
        "label": "Melancholic",
        "search_queries": [
            "Radiohead",
            "The National",
            "Bon Iver",
            "Portishead",
            "Beach House",
        ],
        "est_features": {
            "danceability": 0.38, "energy": 0.29, "valence": 0.18,
            "tempo": 78.0, "acousticness": 0.61, "instrumentalness": 0.08,
            "speechiness": 0.04, "loudness": -10.0,
        },
    },
    "default": {
        "label": "Balanced",
        "search_queries": [
            "Coldplay",
            "Arctic Monkeys",
            "The Killers",
            "Arcade Fire",
            "Vampire Weekend",
        ],
        "est_features": {
            "danceability": 0.65, "energy": 0.58, "valence": 0.55,
            "tempo": 108.0, "acousticness": 0.22, "instrumentalness": 0.05,
            "speechiness": 0.05, "loudness": -6.5,
        },
    },
}

# Artists/labels that flood searches with low-quality compilations
_SPAM_ARTIST_FRAGMENTS = {
    "popular songs", "best music hits", "various artists", "top hits",
    "all stars", "the hits", "the best", "ultimate hits", "musicdream",
    "sing dance", "music hits", "trending music",
}


def _is_spam_track(track: dict[str, Any]) -> bool:
    # Block known spam artist names
    artists_lower = {a["name"].lower() for a in track.get("artists", [])}
    if artists_lower & _SPAM_ARTIST_FRAGMENTS:
        return True
    # Block tracks with suspiciously long names (stock music library keyword stuffing)
    if len(track.get("name", "")) > 100:
        return True
    return False


def _classify_vibe(title: str, description: str, tags: list[str], category_id: str) -> str:
    text = " ".join([title, description, " ".join(tags)]).lower()
    category = _CATEGORY_MAP.get(category_id, "")
    scores: dict[str, int] = {k: 0 for k in _VIBE_KEYWORDS}
    for vibe, keywords in _VIBE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[vibe] += 1
    # Category boosts
    if category in ("gaming", "sports"):
        scores["high_energy"] += 3
    elif category == "music":
        if any(w in text for w in ("lo-fi", "lofi", "ambient", "sleep", "study")):
            scores["relaxing"] += 3
        if any(w in text for w in ("symphony", "orchestral", "strings", "bitter", "indie", "alternative")):
            scores["melancholic"] += 3
        if any(w in text for w in ("party", "dance", "summer", "pop", "feel good")):
            scores["happy"] += 2
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "default"


def _extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|/v/|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot extract a valid video ID from: {url}")


# ─── Mock Fallback Data ─────────────────────────────────────────────────────────

_MOCK_TRACKS: list[dict[str, Any]] = [
    {"id": "4uLU6hMCjMI75M1A2tKUQC", "name": "Never Gonna Give You Up", "artists": ["Rick Astley"], "album": "Whenever You Need Somebody", "preview_url": None, "external_url": "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"},
    {"id": "0VjIjW4GlUZAMYd2vXMi3b", "name": "Blinding Lights", "artists": ["The Weeknd"], "album": "After Hours", "preview_url": None, "external_url": "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"},
    {"id": "7qiZfU4dY1lWllzX7mPBI3", "name": "Shape of You", "artists": ["Ed Sheeran"], "album": "÷ (Divide)", "preview_url": None, "external_url": "https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3"},
]

_MOCK_COMMENTS = [
    {"author": "CoolViewer99", "text": "This is absolutely amazing content!", "like_count": 142, "published_at": "2024-06-01T12:00:00Z"},
    {"author": "RegularWatcher", "text": "Pretty good video overall", "like_count": 54, "published_at": "2024-06-01T13:00:00Z"},
    {"author": "CriticalFan", "text": "Not my favorite but it was okay I guess", "like_count": 8, "published_at": "2024-06-01T14:00:00Z"},
    {"author": "HypeTrainRider", "text": "Wow this is fire!! Absolutely love it!", "like_count": 230, "published_at": "2024-06-01T15:00:00Z"},
    {"author": "NeutralObserver", "text": "Interesting perspective on the topic", "like_count": 17, "published_at": "2024-06-01T16:00:00Z"},
]

_MOCK_AUDIO_FEATURES: dict[str, Any] = {
    "id": "mock_feature",
    "danceability": 0.72, "energy": 0.81, "valence": 0.65,
    "tempo": 128.0, "acousticness": 0.08, "instrumentalness": 0.0,
    "speechiness": 0.04, "loudness": -4.5,
}


def _is_quota_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(x in msg for x in ("quotaexceeded", "429", "quota")) and "commentsdisabled" not in msg


def _is_comments_disabled(e: Exception) -> bool:
    return "commentsdisabled" in str(e).lower()


def _ascii_header(value: str) -> str:
    """HTTP headers must be latin-1; replace unicode punctuation with ASCII equivalents."""
    return value.replace("—", "-").replace("–", "-").encode("ascii", "replace").decode("ascii")


# ─── App ────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Vibe Analyzer API", version="1.0.0", lifespan=lifespan)

_origins = [o.strip() for o in settings.allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Quota-Warning"],
)


# ─── POST /api/vibe-matcher ─────────────────────────────────────────────────────

@app.post("/api/vibe-matcher", response_model=VibeMatcherResponse)
async def vibe_matcher(body: VibeMatcherRequest, request: Request):
    _check_rate(request, "vibe_matcher")

    if body.video_id:
        video_id = body.video_id.strip()
    elif body.youtube_url:
        try:
            video_id = _extract_video_id(body.youtube_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="Provide youtube_url or video_id.")

    cache_key = f"vibe:{video_id}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    # ── Fetch YouTube metadata ──
    try:
        yt = _yt()
        resp = await asyncio.to_thread(
            lambda: yt.videos().list(part="snippet,statistics", id=video_id).execute()
        )
        if not resp.get("items"):
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found.")
        item = resp["items"][0]
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        title: str = snippet.get("title", "")
        description: str = snippet.get("description", "")[:500]
        tags: list[str] = snippet.get("tags", [])[:15]
        category_id: str = snippet.get("categoryId", "0")
        view_count = int(stats.get("viewCount", 0))
        like_count = int(stats.get("likeCount", 0))
    except HTTPException:
        raise
    except Exception as e:
        if _is_quota_error(e):
            result = VibeMatcherResponse(
                video=VideoMetadata(
                    video_id=video_id, title="[Mock — Quota Exceeded]",
                    description="YouTube quota exhausted; showing demo data.",
                    tags=[], category_id="0", view_count=0, like_count=0,
                    vibe_profile=_VIBE_TARGETS["default"],
                ),
                tracks=[SpotifyTrack(**t) for t in _MOCK_TRACKS],
                vibe_label="Balanced (Mock)",
            )
            return JSONResponse(
                content=result.model_dump(),
                headers={"X-Quota-Warning": "YouTube API quota exceeded - mock data returned."},
            )
        raise HTTPException(status_code=500, detail=f"YouTube error: {e}")

    vibe = _classify_vibe(title, description, tags, category_id)
    profile = _VIBE_TARGETS[vibe]

    # ── Spotify track search (recommendations API deprecated Nov 2024) ──
    tracks: list[SpotifyTrack] = []
    try:
        sp = _sp()
        for query in profile["search_queries"]:
            if len(tracks) >= 20:
                break
            results = await asyncio.to_thread(
                lambda q=query: sp.search(q=q, type="track", limit=10)
            )
            for t in results["tracks"]["items"]:
                if len(tracks) >= 20:
                    break
                if any(x.id == t["id"] for x in tracks):
                    continue
                if _is_spam_track(t):
                    continue
                tracks.append(SpotifyTrack(
                    id=t["id"],
                    name=t["name"],
                    artists=[a["name"] for a in t["artists"]],
                    album=t["album"]["name"],
                    preview_url=t.get("preview_url"),
                    external_url=t["external_urls"]["spotify"],
                ))
    except Exception as e:
        if _is_quota_error(e):
            tracks = [SpotifyTrack(**t) for t in _MOCK_TRACKS]
        else:
            raise HTTPException(status_code=500, detail=f"Spotify error: {e}")

    est = profile["est_features"]
    audio_profile = AudioFeatures(
        id=f"estimated_{vibe}",
        danceability=est["danceability"],
        energy=est["energy"],
        valence=est["valence"],
        tempo=est["tempo"],
        acousticness=est["acousticness"],
        instrumentalness=est["instrumentalness"],
        speechiness=est["speechiness"],
        loudness=est["loudness"],
    )

    result = VibeMatcherResponse(
        video=VideoMetadata(
            video_id=video_id, title=title, description=description,
            tags=tags, category_id=category_id,
            view_count=view_count, like_count=like_count,
            vibe_profile={k: v for k, v in profile.items() if k not in ("search_queries", "est_features")},
        ),
        tracks=tracks,
        vibe_label=profile["label"],
        audio_profile=audio_profile,
    )
    _cache.set(cache_key, result)
    return result


# ─── GET /api/youtube/comments/{video_id} ───────────────────────────────────────

@app.get("/api/youtube/comments/{video_id}", response_model=list[Comment])
async def get_comments(video_id: str, request: Request):
    _check_rate(request, "youtube")

    cache_key = f"comments:{video_id}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    try:
        yt = _yt()
        resp = await asyncio.to_thread(
            lambda: yt.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=50,
                order="relevance",
            ).execute()
        )
        comments = [
            Comment(
                author=item["snippet"]["topLevelComment"]["snippet"]["authorDisplayName"],
                text=item["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
                like_count=item["snippet"]["topLevelComment"]["snippet"]["likeCount"],
                published_at=item["snippet"]["topLevelComment"]["snippet"]["publishedAt"],
            )
            for item in resp.get("items", [])
        ]
    except Exception as e:
        if _is_comments_disabled(e):
            mock = [Comment(**c) for c in _MOCK_COMMENTS]
            return JSONResponse(
                content=[c.model_dump() for c in mock],
                headers={"X-Quota-Warning": _ascii_header("Comments are disabled for this video - showing sample data.")},
            )
        if _is_quota_error(e):
            mock = [Comment(**c) for c in _MOCK_COMMENTS]
            return JSONResponse(
                content=[c.model_dump() for c in mock],
                headers={"X-Quota-Warning": _ascii_header("YouTube quota exceeded - showing sample comments.")},
            )
        raise HTTPException(status_code=500, detail=str(e))

    _cache.set(cache_key, comments)
    return comments


# ─── GET /api/spotify/track-features/{track_id} ─────────────────────────────────

@app.get("/api/spotify/track-features/{track_id}", response_model=AudioFeatures)
async def get_track_features(track_id: str, request: Request, vibe: str = "default"):
    """
    Spotify deprecated audio-features for new apps (Nov 2024).
    Returns vibe-profile estimated values; pass ?vibe=<key> for accurate estimates.
    The vibe-matcher endpoint already bundles audio_profile — this endpoint
    exists as a standalone fallback.
    """
    _check_rate(request, "spotify")

    cache_key = f"features:{track_id}:{vibe}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    profile = _VIBE_TARGETS.get(vibe, _VIBE_TARGETS["default"])
    est = profile["est_features"]
    result = AudioFeatures(
        id=track_id,
        danceability=est["danceability"],
        energy=est["energy"],
        valence=est["valence"],
        tempo=est["tempo"],
        acousticness=est["acousticness"],
        instrumentalness=est["instrumentalness"],
        speechiness=est["speechiness"],
        loudness=est["loudness"],
    )
    _cache.set(cache_key, result)
    return result


# ─── GET /health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "cache_size": len(_cache._store)}
