import type { AnnotatedComment, Comment, Sentiment, SentimentBreakdown } from '../types/api';

const POSITIVE = new Set([
  'amazing', 'great', 'love', 'awesome', 'excellent', 'fantastic', 'best',
  'perfect', 'wonderful', 'brilliant', 'incredible', 'outstanding', 'superb',
  'good', 'nice', 'beautiful', 'helpful', 'thanks', 'wow', 'fire', 'goat',
  'legend', 'underrated', 'informative', 'inspiring', 'blessed', 'enjoy',
  'enjoyed', 'favorite', 'incredible', 'mindblowing', 'genius',
]);

const NEGATIVE = new Set([
  'bad', 'terrible', 'awful', 'hate', 'worst', 'horrible', 'disgusting',
  'boring', 'disappointed', 'sucks', 'poor', 'waste', 'trash', 'garbage',
  'useless', 'pathetic', 'overrated', 'clickbait', 'fake', 'wrong', 'error',
  'dislike', 'annoying', 'stupid', 'dumb', 'cringe', 'stop',
]);

export function classifySentiment(text: string): Sentiment {
  const words = text
    .toLowerCase()
    .replace(/[^a-z\s]/g, ' ')
    .split(/\s+/)
    .filter(Boolean);

  let pos = 0;
  let neg = 0;

  for (const word of words) {
    if (POSITIVE.has(word)) pos++;
    if (NEGATIVE.has(word)) neg++;
  }

  if (pos > neg) return 'positive';
  if (neg > pos) return 'negative';
  return 'neutral';
}

export function analyzeComments(comments: Comment[]): {
  breakdown: SentimentBreakdown;
  annotated: AnnotatedComment[];
} {
  const annotated: AnnotatedComment[] = comments.map(c => ({
    ...c,
    sentiment: classifySentiment(c.text),
  }));

  const positive = annotated.filter(c => c.sentiment === 'positive').length;
  const negative = annotated.filter(c => c.sentiment === 'negative').length;
  const neutral = annotated.filter(c => c.sentiment === 'neutral').length;

  return {
    breakdown: { positive, neutral, negative, total: comments.length },
    annotated,
  };
}

export interface VibeSignals {
  happiness: number;
  tension: number;
  chill: number;
  engagement: number;
  energy: number;
}

/** Maps comment sentiment into vibe-axis signals scaled 0–100 */
export function sentimentToVibeSignals(b: SentimentBreakdown): VibeSignals {
  const t = b.total || 1;
  const engagement = Math.round(((b.positive + b.negative) / t) * 100);
  return {
    happiness: Math.round((b.positive / t) * 100),
    tension: Math.round((b.negative / t) * 100),
    chill: Math.round((b.neutral / t) * 100),
    engagement,
    energy: engagement,
  };
}

/** Maps Spotify audio features to same vibe-axis signals scaled 0–100 */
export function featuresToVibeSignals(f: {
  energy: number;
  valence: number;
  danceability: number;
  tempo: number;
  acousticness: number;
}): VibeSignals {
  return {
    happiness: Math.round(f.valence * 100),
    tension: Math.round((1 - f.valence) * 50 + f.energy * 50),
    chill: Math.round(f.acousticness * 100),
    engagement: Math.round((f.danceability * 0.5 + f.energy * 0.5) * 100),
    energy: Math.round(f.energy * 100),
  };
}
