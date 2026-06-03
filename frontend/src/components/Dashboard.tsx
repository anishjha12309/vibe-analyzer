import DOMPurify from 'dompurify';
import type {
  AudioFeatures,
  SpotifyTrack,
  VideoMetadata,
} from '../types/api';
import { useCommentAnalysis } from '../hooks/useCommentAnalysis';
import { useTrackFeatures } from '../hooks/useTrackFeatures';
import { VibeChart } from './VibeChart';

interface Props {
  video: VideoMetadata;
  track: SpotifyTrack;
  audioProfile: AudioFeatures;
}

const SENTIMENT_STYLES = {
  positive: { color: '#22c55e', background: 'rgba(34,197,94,0.06)',  border: 'rgba(34,197,94,0.15)'  },
  neutral:  { color: '#f59e0b', background: 'rgba(245,158,11,0.06)', border: 'rgba(245,158,11,0.15)' },
  negative: { color: '#ef4444', background: 'rgba(239,68,68,0.06)',  border: 'rgba(239,68,68,0.15)'  },
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
  const { comments, breakdown, loading, error } = useCommentAnalysis(video.video_id);
  const features = useTrackFeatures(track.id, audioProfile);

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
                    background: SENTIMENT_STYLES[s].color,
                  }}
                />
              ))}
            </div>

            {/* Sentiment rows */}
            {(['positive', 'neutral', 'negative'] as const).map(s => {
              const styles = SENTIMENT_STYLES[s];
              return (
                <div
                  key={s}
                  className="sentiment-row"
                  style={{
                    background: styles.background,
                    borderColor: styles.border,
                  }}
                >
                  <span style={{ color: styles.color, textTransform: 'capitalize' }}>{s}</span>
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
                  style={{ borderLeftColor: SENTIMENT_STYLES[c.sentiment].color }}
                >
                  <div className="comment-header">
                    <span className="comment-author">{c.author}</span>
                    <span
                      className="comment-sentiment"
                      style={{ color: SENTIMENT_STYLES[c.sentiment].color }}
                    >
                      {c.sentiment}
                    </span>
                  </div>
                  <div
                    className="comment-text"
                    dangerouslySetInnerHTML={{
                      __html: DOMPurify.sanitize(c.text, {
                        ALLOWED_TAGS: ['a', 'b', 'i', 'em', 'strong', 'br'],
                        ALLOWED_ATTR: ['href', 'target', 'rel'],
                      }),
                    }}
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
