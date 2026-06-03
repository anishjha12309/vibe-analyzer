const VIBE_BADGE_COLORS: Record<string, string> = {
  'High Energy':      '#f97316',
  'Chill & Relaxing': '#38bdf8',
  'Happy & Uplifting':'#facc15',
  'Melancholic':      '#818cf8',
  'Balanced':         '#a3a3a3',
};

export function VibeBadge({ label }: { label: string }) {
  const base = Object.keys(VIBE_BADGE_COLORS).find(k => label.startsWith(k)) ?? 'Balanced';
  const color = VIBE_BADGE_COLORS[base] ?? '#a3a3a3';
  return (
    <span
      className="vibe-badge"
      style={{ borderColor: `${color}60`, background: `${color}18`, color }}
    >
      {label}
    </span>
  );
}
