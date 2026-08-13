'use client';

import { useEffect, useRef } from 'react';
import { API_BASE_URL, API_ENDPOINTS } from '@/config/api.config';

// How often an idle-but-visible tab checks in. Mirrors the backend's
// PRESENCE_BEAT_SECONDS; the server keeps counting a user as online for
// PRESENCE_WINDOW_SECONDS (25 min) after their last signal.
const BEAT_MS = 10 * 60 * 1000;

/**
 * Keeps the signed-in user counted as online on the staff dashboard.
 *
 * Nearly all presence comes for free: the axios response interceptor already
 * pings /login-activity/heartbeat after every successful call (throttled 60s),
 * so anyone actually using the app is continuously counted. This hook only
 * covers what that cannot:
 *   - a tab left open while the user reads rather than clicks (the timer), and
 *   - a tab going away, so the count drops them within a second (the leave).
 *
 * Beats only fire while the tab is visible. That keeps the metric meaningful
 * ("has it open and on screen") and sidesteps browsers throttling background
 * timers to ~1/min, which would otherwise cause false drop-offs.
 *
 * Uses raw fetch, never the axios instance, and this is deliberate: axios's
 * response interceptor wipes localStorage and redirects to /login on any 401
 * (see api.service.ts), so a timer beat racing token expiry would throw a
 * reading student out to the login screen. Every failure here is swallowed —
 * presence must never disturb a user.
 */
export function usePresenceHeartbeat(isAuthenticated: boolean): void {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;

    const send = (path: string) => {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      void fetch(`${API_BASE_URL}${path}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        // Survives page unload — and unlike sendBeacon it still carries the header.
        keepalive: true,
      }).catch(() => {
        // Best-effort: the next beat, or window expiry, covers it.
      });
    };

    const beat = () => send(API_ENDPOINTS.LOGIN_ACTIVITY.HEARTBEAT);
    const leave = () => send(API_ENDPOINTS.LOGIN_ACTIVITY.LEAVE);

    const startTimer = () => {
      if (timerRef.current === null) {
        timerRef.current = setInterval(beat, BEAT_MS);
      }
    };
    const stopTimer = () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        beat();
        startTimer();
      } else {
        stopTimer();
        leave();
      }
    };

    if (document.visibilityState === 'visible') {
      beat();
      startTimer();
    }
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', leave);

    return () => {
      stopTimer();
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', leave);
    };
  }, [isAuthenticated]);
}
