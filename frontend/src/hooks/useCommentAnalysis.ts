import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { AnnotatedComment, SentimentBreakdown } from '../types/api';
import { analyzeComments } from '../utils/sentiment';
import { useToast } from './useToast';

interface CommentAnalysis {
  comments: AnnotatedComment[];
  breakdown: SentimentBreakdown | null;
  loading: boolean;
  error: string | null;
}

export function useCommentAnalysis(videoId: string): CommentAnalysis {
  const { addToast } = useToast();
  const [comments, setComments] = useState<AnnotatedComment[]>([]);
  const [breakdown, setBreakdown] = useState<SentimentBreakdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    api.getComments(videoId)
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
  }, [videoId]);

  return { comments, breakdown, loading, error };
}
