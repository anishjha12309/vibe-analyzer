import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { AudioFeatures } from '../types/api';

export function useTrackFeatures(
  trackId: string,
  audioProfile: AudioFeatures,
): AudioFeatures {
  // Extract the vibe key from the profile id: "estimated_high_energy" → "high_energy"
  const vibeKey = audioProfile.id.startsWith('estimated_')
    ? audioProfile.id.slice('estimated_'.length)
    : 'default';

  const [features, setFeatures] = useState<AudioFeatures>(audioProfile);

  useEffect(() => {
    // Reset to the shared vibe profile immediately so the panel doesn't show
    // stale values from the previously selected track while fetching.
    setFeatures(audioProfile);

    api.getTrackFeatures(trackId, vibeKey)
      .then(({ data }) => setFeatures(data))
      .catch(() => {
        // Keep the shared vibe-level estimate as fallback — still useful.
      });
  }, [trackId, vibeKey]);

  return features;
}
