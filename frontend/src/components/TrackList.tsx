import type { SpotifyTrack } from '../types/api';

interface Props {
  tracks: SpotifyTrack[];
  selectedId: string | null;
  onSelect: (track: SpotifyTrack) => void;
}

export function TrackList({ tracks, selectedId, onSelect }: Props) {
  return (
    <div>
      <div className="bento-section-label">MATCHED TRACKS</div>
      <div className="bento-section-title">{tracks.length} tracks found</div>

      <div className="track-grid">
        {tracks.map(track => {
          const isSelected = track.id === selectedId;
          return (
            <button
              key={track.id}
              className={`track-card${isSelected ? ' track-card-selected' : ''}`}
              onClick={() => onSelect(track)}
            >
              <div
                className="track-card-icon"
                style={{
                  background: isSelected ? '#1a3a6b' : 'rgba(26, 58, 107, 0.06)',
                  color: isSelected ? '#fff' : '#8494a7',
                }}
              >
                {isSelected ? '▶' : '♪'}
              </div>

              <div className="track-card-name">{track.name}</div>

              <div className="track-card-artist">
                {track.artists.join(', ')}
              </div>

              <div className="track-card-footer">
                <span className="track-card-album">{track.album}</span>
                <a
                  href={track.external_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link-btn link-btn-spotify"
                  onClick={e => e.stopPropagation()}
                >
                  Open
                </a>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
