export interface SpotifyTrack {
  id: string;
  name: string;
  artists: string[];
  album: string;
  preview_url: string | null;
  external_url: string;
}

export interface VideoMetadata {
  video_id: string;
  title: string;
  description: string;
  tags: string[];
  category_id: string;
  view_count: number;
  like_count: number;
  vibe_profile: Record<string, unknown>;
}

export interface VibeMatcherResponse {
  video: VideoMetadata;
  tracks: SpotifyTrack[];
  vibe_label: string;
  audio_profile: AudioFeatures;
}

export interface Comment {
  author: string;
  text: string;
  like_count: number;
  published_at: string;
}

export interface AudioFeatures {
  id: string;
  danceability: number;
  energy: number;
  valence: number;
  tempo: number;
  acousticness: number;
  instrumentalness: number;
  speechiness: number;
  loudness: number;
}

export interface Toast {
  id: string;
  message: string;
  type: 'warning' | 'error' | 'success' | 'info';
}

export type Sentiment = 'positive' | 'neutral' | 'negative';

export interface SentimentBreakdown {
  positive: number;
  neutral: number;
  negative: number;
  total: number;
}

export interface AnnotatedComment extends Comment {
  sentiment: Sentiment;
}
