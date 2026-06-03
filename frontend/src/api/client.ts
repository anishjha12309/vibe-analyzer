import type { AudioFeatures, Comment, VibeMatcherResponse } from '../types/api';

const BASE: string = import.meta.env.VITE_API_URL ?? '';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface FetchResult<T> {
  data: T;
  quotaWarning: string | null;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<FetchResult<T>> {
  const res = await fetch(`${BASE}${path}`, init);
  const quotaWarning = res.headers.get('X-Quota-Warning');

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText })) as { detail?: string };
    throw new ApiError(body.detail ?? res.statusText, res.status);
  }

  const data = (await res.json()) as T;
  return { data, quotaWarning };
}

function buildVibeBody(input: string): { youtube_url?: string; video_id?: string } {
  const trimmed = input.trim();
  const isUrl = trimmed.includes('youtube.com') || trimmed.includes('youtu.be');
  return isUrl ? { youtube_url: trimmed } : { video_id: trimmed };
}

export const api = {
  matchVibe(input: string) {
    return apiFetch<VibeMatcherResponse>('/api/vibe-matcher', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildVibeBody(input)),
    });
  },

  getComments(videoId: string) {
    return apiFetch<Comment[]>(`/api/youtube/comments/${videoId}`);
  },

  getTrackFeatures(trackId: string, vibe: string) {
    return apiFetch<AudioFeatures>(
      `/api/spotify/track-features/${trackId}?vibe=${encodeURIComponent(vibe)}`,
    );
  },
};
