import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type {
  AnnotatedComment,
  AudioFeatures,
  SentimentBreakdown,
  SpotifyTrack,
  VideoMetadata,
} from '../types/api';
import { analyzeComments } from '../utils/sentiment';
import { useToast } from '../hooks/useToast';
import { VibeChart } from './VibeChart';

interface Props {
  video: VideoMetadata;
  track: SpotifyTrack;
  audioProfile: AudioFeatures;
}

const SENTIMENT_COLOR = {
  positive: '#22c55e',
  neutral: '#f59e0b',
  negative: '#ef4444',
} as const;

function pct(n: number, total: number) {
  return total === 0 ? 0 : Math.round((n / total) * 100);
}

function AudioRow({ label, value, max = 1 }: { label: string; value: number; max?: number }) {
  const normalized = Math.min(1, value / max);
  return (
    <div className="audio-row">
      <div className="audio-row-header">
        <span className="audio-row-label">{label}</span>
        <span className="audio-row-value">
          {max === 1 ? `${Math.round(value * 100)}%` : Math.round(value)}
        </span>
      </div>
      <div className="audio-bar-track">
        <div
          className="audio-bar-fill"
          style={{ width: `${normalized * 100}%` }}
        />
      </div>
    </div>
  );
}

export function Dashboard({ video, track, audioProfile }: Props) {
  const { addToast } = useToast();
  const [comments, setComments] = useState<AnnotatedComment[]>([]);
  const [breakdown, setBreakdown] = useState<SentimentBreakdown | null>(null);
  const [features] = useState<AudioFeatures>(audioProfile);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    api.getComments(video.video_id)
      .then(({ data, quotaWarning }) => {
        if (quotaWarning) addToast(quotaWarning, 'warning');
        const { annotated, breakdown: bd } = analyzeComments(data);
        setComments(annotated);
        setBreakdown(bd);
      })
      .catch(err => {
        const msg = err instanceof Error ? err.message : 'Failed to load comments';
        setError(msg);
        addToast(msg, 'error');
      })
      .finally(() => setLoading(false));
  }, [video.video_id]);

  /* ── Loading state ─────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <div className="loading-text">
          <span className="loading-text-glow">Analyzing comments and audio features…</span>
        </div>
      </div>
    );
  }

  /* ── Error state ───────────────────────────────────────────── */
  if (error) {
    return (
      <div className="error-card">
        <strong>Error:</strong> {error}
      </div>
    );
  }

  /* ── Main content ──────────────────────────────────────────── */
  return (
    <div className="dashboard">
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="dashboard-header">
        <div className="dashboard-header-section">
          <div className="bento-section-label">ANALYZING VIDEO</div>
          <div className="bento-section-title">{video.title}</div>
          <div className="loading-text">
            {video.view_count.toLocaleString()} views · {video.like_count.toLocaleString()} likes
          </div>
        </div>

        <div className="dashboard-header-section">
          <div className="bento-section-label">MATCHED TRACK</div>
          <div className="bento-section-title">{track.name}</div>
          <div className="loading-text">
            {track.artists.join(', ')} · {track.album}
          </div>
        </div>
      </div>

      {/* ── Two-column grid ─────────────────────────────────── */}
      <div className="dashboard-grid">
        {/* ── Sentiment Panel ────────────────────────────────── */}
        {breakdown && (
          <div className="panel">
            <h3 className="panel-title panel-title-primary">
              Comment Sentiment ({breakdown.total} comments)
            </h3>

            {/* Stacked bar */}
            <div className="sentiment-bar">
              {(['positive', 'neutral', 'negative'] as const).map(s => (
                <div
                  key={s}
                  className="sentiment-bar-segment"
                  style={{
                    width: `${pct(breakdown[s], breakdown.total)}%`,
                    background: SENTIMENT_COLOR[s],
                  }}
                />
              ))}
            </div>

            {/* Sentiment rows */}
            {(['positive', 'neutral', 'negative'] as const).map(s => {
              const colorMap = {
                positive: {
                  background: 'rgba(34,197,94,0.06)',
                  border: 'rgba(34,197,94,0.15)',
                  color: '#22c55e',
                },
                neutral: {
                  background: 'rgba(245,158,11,0.06)',
                  border: 'rgba(245,158,11,0.15)',
                  color: '#f59e0b',
                },
                negative: {
                  background: 'rgba(239,68,68,0.06)',
                  border: 'rgba(239,68,68,0.15)',
                  color: '#ef4444',
                },
              } as const;

              const c = colorMap[s];
              return (
                <div
                  key={s}
                  className="sentiment-row"
                  style={{
                    background: c.background,
                    borderColor: c.border,
                  }}
                >
                  <span style={{ color: c.color, textTransform: 'capitalize' }}>{s}</span>
                  <span style={{ fontWeight: 600 }}>
                    {breakdown[s]} ({pct(breakdown[s], breakdown.total)}%)
                  </span>
                </div>
              );
            })}

            {/* Comment list */}
            <div className="comment-list">
              {comments.map((c, i) => (
                <div
                  key={i}
                  className="comment-card"
                  style={{ borderLeftColor: SENTIMENT_COLOR[c.sentiment] }}
                >
                  <div className="comment-header">
                    <span className="comment-author">{c.author}</span>
                    <span
                      className="comment-sentiment"
                      style={{ color: SENTIMENT_COLOR[c.sentiment] }}
                    >
                      {c.sentiment}
                    </span>
                  </div>
                  <div
                    className="comment-text"
                    dangerouslySetInnerHTML={{ __html: c.text }}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Audio Features Panel ──────────────────────────── */}
        {features && (
          <div className="panel">
            <h3 className="panel-title panel-title-secondary">
              Spotify Audio Features
            </h3>

            <AudioRow label="Valence (Positivity)" value={features.valence} />
            <AudioRow label="Energy" value={features.energy} />
            <AudioRow label="Danceability" value={features.danceability} />
            <AudioRow label="Acousticness" value={features.acousticness} />
            <AudioRow label="Instrumentalness" value={features.instrumentalness} />
            <AudioRow label="Speechiness" value={features.speechiness} />
            <AudioRow label="Tempo (BPM)" value={features.tempo} max={220} />

            {/* Stats grid */}
            <div className="audio-stats-grid">
              {[
                { label: 'Tempo', value: `${Math.round(features.tempo)} BPM` },
                { label: 'Loudness', value: `${features.loudness.toFixed(1)} dB` },
              ].map(item => (
                <div key={item.label} className="audio-stat-card">
                  <div className="audio-row-label">{item.label}</div>
                  <div className="audio-row-value" style={{ fontSize: '1rem', fontWeight: 700 }}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Vibe Chart ──────────────────────────────────────── */}
      {breakdown && features && <VibeChart sentiment={breakdown} features={features} />}
    </div>
  );
}
