from __future__ import annotations

import asyncio
import hashlib
import random as _random
import re
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any

import spotipy
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from googleapiclient.discovery import build
from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings
from starlette.middleware.base import BaseHTTPMiddleware
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

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def ttl(self) -> int:
        return self._ttl


_cache = TTLCache()


# ─── Rolling-Window Rate Limiter ────────────────────────────────────────────────

class RollingWindowLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, dict[str, list[float]]] = {}

    def is_allowed(
        self, ip: str, group: str, max_requests: int, window: int = 60
    ) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, reset_in_seconds)."""
        now = time.monotonic()
        self._windows.setdefault(ip, {}).setdefault(group, [])
        self._windows[ip][group] = [t for t in self._windows[ip][group] if now - t < window]
        current = self._windows[ip][group]
        oldest = min(current) if current else now
        reset_in = max(0, int(window - (now - oldest)))
        if len(current) >= max_requests:
            return False, 0, reset_in
        self._windows[ip][group].append(now)
        remaining = max_requests - len(self._windows[ip][group])
        return True, remaining, reset_in


_limiter = RollingWindowLimiter()
_LIMITS: dict[str, int] = {"vibe_matcher": 5, "youtube": 10, "spotify": 10}


def _check_rate(request: Request, group: str) -> dict[str, str]:
    """Enforces rate limit; returns RateLimit headers to attach to the response."""
    ip = request.client.host if request.client else "unknown"
    limit = _LIMITS.get(group, 10)
    allowed, remaining, reset_in = _limiter.is_allowed(ip, group, limit)
    rl_headers = {
        "RateLimit-Limit": str(limit),
        "RateLimit-Remaining": str(remaining),
        "RateLimit-Reset": str(reset_in),
    }
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {limit} req/min for {group}. Try again shortly.",
            headers=rl_headers,
        )
    return rl_headers




# ─── Pydantic Schemas ───────────────────────────────────────────────────────────

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


class VibeProfile(BaseModel):
    label: str


class ResponseMeta(BaseModel):
    degraded: bool = False
    warning: str | None = None


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
    vibe_profile: VibeProfile


class VibeMatcherResponse(BaseModel):
    video: VideoMetadata
    tracks: list[SpotifyTrack]
    vibe_label: str
    audio_profile: AudioFeatures  # vibe-estimated (Spotify audio-features deprecated Nov 2024)
    meta: ResponseMeta = ResponseMeta()


class Comment(BaseModel):
    author: str
    text: str
    like_count: int
    published_at: str


class VibeMatcherRequest(BaseModel):
    youtube_url: str | None = None
    video_id: str | None = None

    @field_validator("video_id")
    @classmethod
    def validate_video_id(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"[A-Za-z0-9_-]{11}", v.strip()):
            raise ValueError("video_id must be exactly 11 alphanumeric/dash/underscore characters")
        return v.strip() if v else v

    @model_validator(mode="after")
    def require_one_input(self) -> "VibeMatcherRequest":
        if not self.youtube_url and not self.video_id:
            raise ValueError("Provide either youtube_url or video_id")
        return self


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
        # common in real music videos / descriptions
        "remix", "bass", "trap", "hip hop", "hip-hop", "rap", "metal",
        "punk", "electronic", "club", "banger", "drill", "hard rock",
        "rock", "indie rock", "alternative rock", "punk rock", "rave",
        "feat", "featuring", "official music video", "music video",
    ],
    "relaxing": [
        "lofi", "lo-fi", "chill", "relax", "sleep", "calm", "nature",
        "ambient", "cozy", "study", "peaceful", "meditation", "rain",
        "soft", "gentle", "slow", "acoustic", "jazz", "classical",
        # common in real acoustic/instrumental content
        "piano", "unplugged", "instrumental", "background music",
        "focus", "spa", "yoga", "cover", "stripped", "live session",
        "session", "acoustic version", "piano version",
    ],
    "happy": [
        "funny", "comedy", "laugh", "happy", "joy", "celebration", "party",
        "fun", "vlog", "travel", "adventure", "positive", "wholesome",
        "dance", "pop", "summer", "upbeat", "feel good",
        # common in upbeat pop videos
        "good vibes", "cheerful", "catchy", "pop music", "feel-good",
        "official video", "lyric video", "bouncy", "bright",
    ],
    "melancholic": [
        "sad", "emotional", "depression", "anxiety", "loss", "grief",
        "heartbreak", "lonely", "nostalgic", "melancholy", "bitter",
        "symphony", "orchestral", "strings", "cinematic", "indie",
        "alternative", "grunge", "dark", "reflection", "sorrow",
        # common in ballads / singer-songwriter content
        "ballad", "slow song", "love song", "miss you", "breakup",
        "heartbroken", "tears", "hurt", "pain", "alone", "folk",
        "acoustic ballad", "piano ballad", "singer-songwriter",
    ],
}

_VIBE_TARGETS: dict[str, dict[str, Any]] = {
    "high_energy": {
        "label": "High Energy",
        "search_queries": [
            "Skrillex", "Daft Punk", "The Prodigy", "Calvin Harris", "Avicii",
            "Marshmello", "Diplo", "Chemical Brothers", "Fatboy Slim", "Nine Inch Nails",
            "Eminem", "Kendrick Lamar", "Metallica", "Linkin Park", "Imagine Dragons",
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
            "Nils Frahm", "Ludovico Einaudi", "Olafur Arnalds", "Tycho", "Brian Eno",
            "Max Richter", "Johann Johannsson", "Explosions in the Sky", "Agnes Obel", "Moby",
            "Cigarettes After Sex", "Nick Drake", "Sufjan Stevens", "Hans Zimmer", "Hammock",
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
            "Pharrell Williams", "Bruno Mars", "Dua Lipa", "Harry Styles", "Lizzo",
            "Taylor Swift", "Ed Sheeran", "Katy Perry", "Ariana Grande", "Justin Timberlake",
            "Michael Jackson", "Stevie Wonder", "Mark Ronson", "Earth Wind Fire", "Beyonce",
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
            "Radiohead", "The National", "Bon Iver", "Portishead", "Beach House",
            "Elliott Smith", "Nick Cave", "Joy Division", "Sigur Ros", "Mazzy Star",
            "Lana Del Rey", "Fleet Foxes", "Phoebe Bridgers", "Iron and Wine", "Daughter",
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
            "Coldplay", "Arctic Monkeys", "The Killers", "Arcade Fire", "Vampire Weekend",
            "Tame Impala", "Mac DeMarco", "Kings of Leon", "The Strokes", "Franz Ferdinand",
            "MGMT", "Phoenix", "Foster the People", "alt-J", "Two Door Cinema Club",
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


def _classify_vibe(title: str, description: str, tags: list[str], category_id: str, video_id: str = "") -> str:
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
        if any(w in text for w in ("lo-fi", "lofi", "ambient", "sleep", "study", "piano", "acoustic", "instrumental", "cover", "classical", "jazz")):
            scores["relaxing"] += 3
        if any(w in text for w in ("symphony", "orchestral", "strings", "bitter", "indie", "alternative", "ballad", "sad", "heartbreak", "folk", "singer-songwriter")):
            scores["melancholic"] += 3
        if any(w in text for w in ("party", "dance", "summer", "pop", "feel good", "happy", "upbeat", "catchy")):
            scores["happy"] += 2
        if any(w in text for w in ("remix", "trap", "bass", "edm", "electronic", "rock", "metal", "drill", "hip hop", "hip-hop", "rap")):
            scores["high_energy"] += 2
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best
    # Deterministic fallback: hash the video_id so different videos get different vibes
    # rather than every unclassified video always returning "default"
    _vibes = ["high_energy", "relaxing", "happy", "melancholic", "default"]
    idx = int(hashlib.md5((video_id or title).encode()).hexdigest()[:2], 16) % len(_vibes)
    return _vibes[idx]


def _extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|/v/|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot extract a valid video ID from: {url}")


def _vary_features(base: dict[str, float], track_id: str) -> dict[str, float]:
    """Apply deterministic per-track variation to vibe-level baseline estimates.

    Since Spotify deprecated audio-features for new apps (Nov 2024) there are no
    real per-track values available.  We seed a PRNG from the track_id hash so
    every track gets a stable, unique fingerprint that still reflects the vibe
    category (±8 % for 0-1 features, ±12 BPM for tempo, ±2 dB for loudness).
    """
    seed = int(hashlib.md5(track_id.encode()).hexdigest()[:8], 16)
    rng = _random.Random(seed)
    result: dict[str, float] = {}
    for key, val in base.items():
        if key == "tempo":
            result[key] = round(max(60.0, min(200.0, val + rng.uniform(-12.0, 12.0))), 1)
        elif key == "loudness":
            result[key] = round(max(-20.0, min(-1.0, val + rng.uniform(-2.0, 2.0))), 1)
        else:
            result[key] = round(max(0.0, min(1.0, val + rng.uniform(-0.08, 0.08))), 2)
    return result


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
    app.state.yt = build("youtube", "v3", developerKey=settings.youtube_api_key)
    app.state.sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=settings.spotify_client_id,
            client_secret=settings.spotify_client_secret,
        )
    )
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
    expose_headers=[
        "X-Quota-Warning",
        "X-Next-Page-Token",
        "RateLimit-Limit",
        "RateLimit-Remaining",
        "RateLimit-Reset",
        "Cache-Control",
    ],
)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(_SecurityHeadersMiddleware)


def get_yt(request: Request):
    return request.app.state.yt


def get_sp(request: Request) -> spotipy.Spotify:
    return request.app.state.sp


# ─── POST /api/vibe-matcher ─────────────────────────────────────────────────────

@app.post(
    "/api/vibe-matcher",
    response_model=VibeMatcherResponse,
    summary="Match a YouTube video to Spotify tracks by vibe",
    tags=["Vibe"],
    responses={
        400: {"description": "Invalid or missing youtube_url / video_id"},
        404: {"description": "YouTube video not found"},
        422: {"description": "Validation error (e.g. malformed video_id)"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Upstream YouTube or Spotify error"},
    },
)
async def vibe_matcher(
    body: VibeMatcherRequest,
    request: Request,
    response: Response,
    yt=Depends(get_yt),
    sp: spotipy.Spotify = Depends(get_sp),
):
    """Classify the vibe of a YouTube video and return up to 20 matching Spotify tracks.
    Pass either a full YouTube URL or an 11-character video ID. Results are cached for 5 minutes."""
    rl_headers = _check_rate(request, "vibe_matcher")
    for k, v in rl_headers.items():
        response.headers[k] = v

    if body.video_id:
        video_id = body.video_id
    else:
        try:
            video_id = _extract_video_id(body.youtube_url)  # type: ignore[arg-type]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    cache_key = f"vibe:{video_id}"
    hit, cached = _cache.get(cache_key)
    if hit:
        return cached

    _mock_est = _VIBE_TARGETS["default"]["est_features"]
    _mock_audio = AudioFeatures(id="estimated_default", **_mock_est)

    # ── Fetch YouTube metadata ──
    try:
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
            response.headers["X-Quota-Warning"] = "YouTube API quota exceeded - mock data returned."
            return VibeMatcherResponse(
                video=VideoMetadata(
                    video_id=video_id, title="Demo Video",
                    description="YouTube quota exhausted; showing demo data.",
                    tags=[], category_id="0", view_count=0, like_count=0,
                    vibe_profile=VibeProfile(label="Balanced"),
                ),
                tracks=[SpotifyTrack(**t) for t in _MOCK_TRACKS],
                vibe_label="Balanced",
                audio_profile=_mock_audio,
                meta=ResponseMeta(degraded=True, warning="YouTube API quota exceeded."),
            )
        raise HTTPException(status_code=500, detail=f"YouTube error: {e}")

    vibe = _classify_vibe(title, description, tags, category_id, video_id)
    profile = _VIBE_TARGETS[vibe]

    # ── Spotify track search (recommendations API deprecated Nov 2024) ──
    _rng = _random.Random(video_id)
    queries = _rng.sample(profile["search_queries"], min(5, len(profile["search_queries"])))

    tracks: list[SpotifyTrack] = []
    try:
        for query in queries:
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
            vibe_profile=VibeProfile(label=profile["label"]),
        ),
        tracks=tracks,
        vibe_label=profile["label"],
        audio_profile=audio_profile,
    )
    _cache.set(cache_key, result)
    return result


# ─── GET /api/youtube/comments/{video_id} ───────────────────────────────────────

@app.get(
    "/api/youtube/comments/{video_id}",
    response_model=list[Comment],
    summary="Fetch top comments for a YouTube video",
    tags=["YouTube"],
    responses={
        429: {"description": "Rate limit exceeded"},
        500: {"description": "YouTube API error"},
    },
)
async def get_comments(
    video_id: str,
    request: Request,
    response: Response,
    yt=Depends(get_yt),
    limit: int = Query(default=50, ge=1, le=100, description="Number of comments to return (1–100)"),
):
    """Returns top-level comments sorted by relevance.
    If comments are disabled or quota is exceeded the response falls back to sample data
    and sets X-Quota-Warning. If more comments exist, X-Next-Page-Token is set."""
    rl_headers = _check_rate(request, "youtube")
    for k, v in rl_headers.items():
        response.headers[k] = v

    cache_key = f"comments:{video_id}:{limit}"
    hit, cached = _cache.get(cache_key)
    if hit:
        response.headers["Cache-Control"] = f"public, max-age={_cache.ttl}"
        return cached

    try:
        resp = await asyncio.to_thread(
            lambda: yt.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=limit,
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
        next_page_token = resp.get("nextPageToken")
        if next_page_token:
            response.headers["X-Next-Page-Token"] = next_page_token
    except Exception as e:
        if _is_comments_disabled(e):
            response.headers["X-Quota-Warning"] = _ascii_header(
                "Comments are disabled for this video - showing sample data."
            )
            return [Comment(**c) for c in _MOCK_COMMENTS]
        if _is_quota_error(e):
            response.headers["X-Quota-Warning"] = _ascii_header(
                "YouTube quota exceeded - showing sample comments."
            )
            return [Comment(**c) for c in _MOCK_COMMENTS]
        raise HTTPException(status_code=500, detail=str(e))

    _cache.set(cache_key, comments)
    response.headers["Cache-Control"] = f"public, max-age={_cache.ttl}"
    return comments


# ─── GET /api/spotify/track-features/{track_id} ─────────────────────────────────

@app.get(
    "/api/spotify/track-features/{track_id}",
    response_model=AudioFeatures,
    summary="Get estimated audio features for a track by vibe",
    tags=["Spotify"],
    responses={
        429: {"description": "Rate limit exceeded"},
    },
)
async def get_track_features(
    track_id: str,
    request: Request,
    response: Response,
    vibe: str = Query(
        default="default",
        description="Vibe key: high_energy | relaxing | happy | melancholic | default",
    ),
):
    """Returns estimated audio features derived from the vibe profile.
    Spotify deprecated real audio-features for new apps in Nov 2024.
    The vibe-matcher endpoint already bundles audio_profile — use this
    endpoint only as a standalone fallback."""
    rl_headers = _check_rate(request, "spotify")
    for k, v in rl_headers.items():
        response.headers[k] = v

    cache_key = f"features:{track_id}:{vibe}"
    hit, cached = _cache.get(cache_key)
    if hit:
        response.headers["Cache-Control"] = f"public, max-age={_cache.ttl}"
        return cached

    profile = _VIBE_TARGETS.get(vibe, _VIBE_TARGETS["default"])
    varied = _vary_features(profile["est_features"], track_id)
    result = AudioFeatures(
        id=track_id,
        danceability=varied["danceability"],
        energy=varied["energy"],
        valence=varied["valence"],
        tempo=varied["tempo"],
        acousticness=varied["acousticness"],
        instrumentalness=varied["instrumentalness"],
        speechiness=varied["speechiness"],
        loudness=varied["loudness"],
    )
    _cache.set(cache_key, result)
    response.headers["Cache-Control"] = f"public, max-age={_cache.ttl}"
    return result


# ─── GET /health ────────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check", tags=["System"])
async def health():
    """Returns service status and current in-memory cache size."""
    return {"status": "ok", "cache_size": _cache.size}
