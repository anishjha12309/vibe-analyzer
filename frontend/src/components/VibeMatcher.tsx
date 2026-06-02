import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { SpotifyTrack, VibeMatcherResponse } from '../types/api';
import { useToast } from '../hooks/useToast';
import { TrackList } from './TrackList';
import { Dashboard } from './Dashboard';

const VIBE_BADGE_COLORS: Record<string, string> = {
  'High Energy': '#f97316',
  'Chill & Relaxing': '#38bdf8',
  'Happy & Uplifting': '#facc15',
  'Melancholic': '#818cf8',
  'Balanced': '#a3a3a3',
};

function VibeBadge({ label }: { label: string }) {
  const base = Object.keys(VIBE_BADGE_COLORS).find(k => label.startsWith(k)) ?? 'Balanced';
  const color = VIBE_BADGE_COLORS[base] ?? '#a3a3a3';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.2rem 0.65rem',
        borderRadius: '999px',
        border: `1px solid ${color}60`,
        background: `${color}18`,
        color,
        fontSize: '0.75rem',
        fontWeight: 600,
      }}
    >
      {label}
    </span>
  );
}

export function VibeMatcher() {
  const { addToast } = useToast();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VibeMatcherResponse | null>(null);
  const [selectedTrack, setSelectedTrack] = useState<SpotifyTrack | null>(null);
  const [showDashboard, setShowDashboard] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;

    setLoading(true);
    setResult(null);
    setSelectedTrack(null);
    setShowDashboard(false);

    const isUrl = trimmed.includes('youtube.com') || trimmed.includes('youtu.be');
    const body = isUrl ? { youtube_url: trimmed } : { video_id: trimmed };

    try {
      const { data, quotaWarning } = await api.matchVibe(body);
      if (quotaWarning) addToast(quotaWarning, 'warning');
      setResult(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        addToast('Rate limit hit — wait a moment and try again.', 'warning');
      } else {
        const msg = err instanceof Error ? err.message : 'Unknown error';
        addToast(msg, 'error');
      }
    } finally {
      setLoading(false);
    }
  }

  function handleTrackSelect(track: SpotifyTrack) {
    setSelectedTrack(track);
    setShowDashboard(false);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Input form */}
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="YouTube URL or video ID (e.g. dQw4w9WgXcQ)"
          disabled={loading}
          style={{
            flex: 1,
            background: '#111118',
            border: '1px solid #2a2a3a',
            borderRadius: '0.5rem',
            color: '#f0f0f5',
            padding: '0.65rem 1rem',
            fontSize: '0.875rem',
            outline: 'none',
            transition: 'border-color 0.15s',
          }}
          onFocus={e => (e.target.style.borderColor = '#6d28d9')}
          onBlur={e => (e.target.style.borderColor = '#2a2a3a')}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          style={{
            background: loading ? '#374151' : 'linear-gradient(135deg, #6d28d9, #ec4899)',
            color: '#fff',
            border: 'none',
            borderRadius: '0.5rem',
            padding: '0.65rem 1.5rem',
            fontSize: '0.875rem',
            fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {loading ? 'Analyzing…' : 'Match Vibe'}
        </button>
      </form>

      {/* Results */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Video card */}
          <div
            style={{
              background: '#111118',
              border: '1px solid #2a2a3a',
              borderRadius: '0.75rem',
              padding: '1.25rem',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: '1rem',
                flexWrap: 'wrap',
              }}
            >
              <div>
                <div style={{ color: '#6b7280', fontSize: '0.72rem', marginBottom: '0.25rem' }}>
                  YOUTUBE VIDEO
                </div>
                <h2 style={{ color: '#f0f0f5', fontSize: '1rem', fontWeight: 700, marginBottom: '0.4rem' }}>
                  {result.video.title}
                </h2>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <VibeBadge label={result.vibe_label} />
                  <span style={{ color: '#6b7280', fontSize: '0.75rem' }}>
                    {result.video.view_count.toLocaleString()} views ·{' '}
                    {result.video.like_count.toLocaleString()} likes
                  </span>
                </div>
              </div>
              <a
                href={`https://www.youtube.com/watch?v=${result.video.video_id}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: '#ff4444',
                  fontSize: '0.75rem',
                  textDecoration: 'none',
                  padding: '0.3rem 0.6rem',
                  border: '1px solid #ff444440',
                  borderRadius: '0.3rem',
                  whiteSpace: 'nowrap',
                }}
              >
                ▶ YouTube
              </a>
            </div>

            {result.video.tags.length > 0 && (
              <div style={{ marginTop: '0.75rem', display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                {result.video.tags.slice(0, 8).map(tag => (
                  <span
                    key={tag}
                    style={{
                      background: '#1a1a2e',
                      border: '1px solid #2a2a3a',
                      borderRadius: '0.3rem',
                      padding: '0.15rem 0.5rem',
                      fontSize: '0.7rem',
                      color: '#9ca3af',
                    }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Track list */}
          <div
            style={{
              background: '#111118',
              border: '1px solid #2a2a3a',
              borderRadius: '0.75rem',
              padding: '1.25rem',
            }}
          >
            <TrackList
              tracks={result.tracks}
              selectedId={selectedTrack?.id ?? null}
              onSelect={handleTrackSelect}
            />
          </div>

          {/* Deep-analyze CTA */}
          {selectedTrack && !showDashboard && (
            <button
              onClick={() => setShowDashboard(true)}
              style={{
                background: 'linear-gradient(135deg, #6d28d9, #ec4899)',
                color: '#fff',
                border: 'none',
                borderRadius: '0.5rem',
                padding: '0.75rem',
                fontSize: '0.9rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Deep Analyze: "{selectedTrack.name}"
            </button>
          )}
        </div>
      )}

      {/* Dashboard */}
      {showDashboard && result && selectedTrack && (
        <Dashboard
          video={result.video}
          track={selectedTrack}
          audioProfile={result.audio_profile}
        />
      )}
    </div>
  );
}
