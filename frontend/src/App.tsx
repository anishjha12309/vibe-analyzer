import { useState, useRef, useEffect } from 'react';
import { api, ApiError } from './api/client';
import type { SpotifyTrack, VibeMatcherResponse } from './types/api';
import { useToast } from './hooks/useToast';
import { ToastProvider } from './hooks/useToast';
import { TrackList } from './components/TrackList';
import { Dashboard } from './components/Dashboard';
import { VibeBadge } from './components/VibeBadge';
import { useLenis } from './hooks/useLenis';
import { useScrollReveal } from './hooks/useScrollReveal';

/* ─── Inner app (needs toast context) ─── */
function VibeApp() {
  useLenis();
  useScrollReveal();

  const { addToast } = useToast();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VibeMatcherResponse | null>(null);
  const [selectedTrack, setSelectedTrack] = useState<SpotifyTrack | null>(null);
  const [showDashboard, setShowDashboard] = useState(false);

  const resultsRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);

  /* scroll to results when they arrive */
  useEffect(() => {
    if (result && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [result]);

  /* nav scroll state */
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;

    const onScroll = () => {
      nav.classList.toggle('nav-scrolled', window.scrollY > 60);
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;

    setLoading(true);
    setResult(null);
    setSelectedTrack(null);
    setShowDashboard(false);

    try {
      const { data, quotaWarning } = await api.matchVibe(trimmed);
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
    <div className="app-root">
      {/* ═══════════════════  NAV  ═══════════════════ */}
      <nav className="nav" ref={navRef}>
        <div className="nav-left">
          <div className="nav-logo-icon">◈</div>
          <span className="nav-brand">Vibe Analyzer</span>
        </div>
        <div className="nav-center">YOUTUBE × SPOTIFY</div>
        <div className="nav-right">
          <div className="nav-status" />
        </div>
      </nav>

      {/* ═══════════════════  MAIN  ═══════════════════ */}
      <main>
      {/* ═══════════════════  HERO  ═══════════════════ */}
      <section className="hero" style={{ backgroundImage: `url(/hero_bg.webp)` }}>
        <div className="hero-content">
          <div className="hero-pill">
            <span className="hero-pill-dot">●</span> AI-POWERED VIBE MATCHING
          </div>

          <h1 className="hero-headline">
            <span className="hero-line">Crafting</span>
            <span className="hero-line">soundtracks</span>
            <span className="hero-line">through</span>
            <em className="hero-line hero-headline-accent">vibes</em>
          </h1>

          <p className="hero-subtitle">
            Paste a YouTube URL — we'll decode its energy, mood, and rhythm, then
            surface Spotify tracks that resonate with the same vibe.
          </p>

          {/* Search bar */}
          <form className="search-bar" onSubmit={handleSubmit}>
            <div className="search-bar-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </div>
            <input
              className="search-bar-input"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="YouTube URL or video ID (e.g. dQw4w9WgXcQ)"
              disabled={loading}
            />
            <button
              className="search-bar-btn"
              type="submit"
              disabled={loading || !input.trim()}
            >
              {loading ? (
                <span className="search-bar-spinner" />
              ) : (
                'Match Vibe'
              )}
            </button>
          </form>
        </div>

        {/* Scroll indicator */}
        <div className="hero-scroll-indicator">
          <div className="hero-scroll-line" />
          <div className="hero-scroll-arrow" />
        </div>
      </section>

      {/* ═══════════════════  RESULTS  ═══════════════════ */}
      {result && (
        <section className="results-section" ref={resultsRef}>
          <div className="results-inner">
            <span className="results-label">RESULTS</span>
            <h2 className="results-heading">Vibe Match Complete</h2>

            {/* Video card */}
            <div className="result-video-card">
              <div className="result-video-header">
                <div>
                  <div className="result-video-eyebrow">YOUTUBE VIDEO</div>
                  <h3 className="result-video-title">{result.video.title}</h3>
                  <div className="result-video-meta">
                    <VibeBadge label={result.vibe_label} />
                    <span className="result-video-stats">
                      {result.video.view_count.toLocaleString()} views ·{' '}
                      {result.video.like_count.toLocaleString()} likes
                    </span>
                  </div>
                </div>
                <a
                  href={`https://www.youtube.com/watch?v=${result.video.video_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="result-youtube-link"
                >
                  ▶ YouTube
                </a>
              </div>

              {result.video.tags.length > 0 && (
                <div className="result-tags">
                  {result.video.tags.slice(0, 8).map((tag) => (
                    <span key={tag} className="result-tag">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Track grid (bento) */}
            <div className="result-tracks-card">
              <TrackList
                tracks={result.tracks}
                selectedId={selectedTrack?.id ?? null}
                onSelect={handleTrackSelect}
              />
            </div>

            {/* Deep-analyze CTA */}
            {selectedTrack && !showDashboard && (
              <button
                className="deep-analyze-btn"
                onClick={() => setShowDashboard(true)}
              >
                Deep Analyze: "{selectedTrack.name}"
              </button>
            )}

            {/* Dashboard */}
            {showDashboard && result && selectedTrack && (
              <div className="dashboard-wrapper">
                <Dashboard
                  video={result.video}
                  track={selectedTrack}
                  audioProfile={result.audio_profile}
                />
              </div>
            )}
          </div>
        </section>
      )}

      </main>

      {/* ═══════════════════  FOOTER  ═══════════════════ */}
      <footer className="footer reveal">
        <div className="footer-inner">
          <div className="footer-brand">
            <div className="footer-logo">
              <div className="nav-logo-icon">◈</div>
              <span className="nav-brand">Vibe Analyzer</span>
            </div>
            <p className="footer-brand-desc">
              Decoding the energy of video content and connecting you with music
              that resonates. AI-powered vibe matching at its finest.
            </p>
          </div>

          <div className="footer-bottom">
            <p className="footer-copy">
              © 2026 Built by Anish · All rights reserved
            </p>
            <div className="footer-socials">
              <button className="footer-social-btn" aria-label="GitHub">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                </svg>
              </button>
              <button className="footer-social-btn" aria-label="Twitter">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
              </button>
              <button className="footer-social-btn" aria-label="LinkedIn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* ─── Root wrapper (provides toast context) ─── */
export default function App() {
  return (
    <ToastProvider>
      <VibeApp />
    </ToastProvider>
  );
}
