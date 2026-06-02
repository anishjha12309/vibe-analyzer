import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { AudioFeatures } from '../types/api';
import type { SentimentBreakdown } from '../types/api';
import { featuresToVibeSignals, sentimentToVibeSignals } from '../utils/sentiment';

interface Props {
  sentiment: SentimentBreakdown;
  features: AudioFeatures;
}

const CHART_METRICS = [
  {
    key: 'happiness',
    label: 'Happiness',
    desc: 'Comment positivity vs track valence',
  },
  {
    key: 'energy',
    label: 'Energy',
    desc: 'Comment engagement vs audio energy',
  },
  {
    key: 'chill',
    label: 'Chill',
    desc: 'Neutral comments vs acousticness',
  },
  {
    key: 'tension',
    label: 'Tension',
    desc: 'Negative comments vs inverse valence/energy',
  },
  {
    key: 'engagement',
    label: 'Groove',
    desc: 'Viewer engagement vs danceability+energy',
  },
] as const;

export function VibeChart({ sentiment, features }: Props) {
  const commentSignals = sentimentToVibeSignals(sentiment);
  const audioSignals = featuresToVibeSignals(features);

  const data = CHART_METRICS.map(m => ({
    name: m.label,
    'Comment Signal': commentSignals[m.key as keyof typeof commentSignals] ?? 0,
    'Audio Feature':
      m.key === 'energy'
        ? audioSignals.energy
        : (audioSignals[m.key as keyof typeof audioSignals] ?? 0),
  }));

  return (
    <div className="chart-panel">
      <h3 className="chart-title">
        Vibe Balance Chart
      </h3>
      <p className="chart-subtitle" style={{ fontStyle: 'italic' }}>
        YouTube comment signals vs Spotify audio features — scaled 0–100
      </p>

      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} barCategoryGap="30%" barGap={4}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: '#6b7280', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: '#6b7280', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={30}
          />
          <Tooltip
            contentStyle={{
              background: 'rgba(255, 255, 255, 0.95)',
              border: '1px solid rgba(26, 58, 107, 0.12)',
              borderRadius: '12px',
              color: '#0f1a2e',
              fontSize: '0.8rem',
              backdropFilter: 'blur(10px)',
            }}
            formatter={(val: number, name: string) => [`${val}%`, name]}
          />
          <Legend
            wrapperStyle={{ fontSize: '0.8rem', color: '#9ca3af', paddingTop: '0.75rem' }}
          />
          <Bar dataKey="Comment Signal" fill="#1a3a6b" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Audio Feature" fill="#4a8eff" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>

      <div className="chart-metrics-grid">
        {CHART_METRICS.map(m => (
          <div key={m.key} className="chart-metric-card">
            <div className="chart-metric-label">
              {m.label}
            </div>
            <div className="chart-metric-desc">
              {m.desc}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
