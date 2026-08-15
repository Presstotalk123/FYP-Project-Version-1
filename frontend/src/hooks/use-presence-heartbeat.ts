'use client';

import { useEffect, useRef } from 'react';
import { API_BASE_URL, API_ENDPOINTS } from '@/config/api.config';
import {
  HEARTBEAT_THROTTLE_MS,
  clearHeartbeatSent,
  getLastHeartbeatAt,
  markHeartbeatSent,
} from '@/services/loginActivity.service';

// How often an idle-but-visible tab checks in. Mirrors the backend's
// PRESENCE_BEAT_SECONDS; the server keeps counting a user as online for
// PRESENCE_WINDOW_SECONDS (25 min) after their last signal.
const BEAT_MS = 10 * 60 * 1000;

// Random spread applied to each tick so many tabs that opened around the same
// moment (a whole class joining an assessment at once) don't keep ticking in
// lockstep every 10 minutes forever. Each tick is scheduled BEAT_MS ± JITTER_MS
// from the last one, using a fresh random offset every time (not a fixed
// per-tab offset), so the beats drift apart over the session instead of
// staying bunched at whatever second they happened to start on.
const JITTER_MS = 2 * 60 * 1000;

function nextDelay(): number {
  return BEAT_MS + (Math.random() * 2 - 1) * JITTER_MS;
}

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
 * The timer skips a beat if a heartbeat (from either source) already went out
 * in the last HEARTBEAT_THROTTLE_MS: a student actively working almost never
 * needs the timer's beat at all, since their action-triggered pings already
 * cover it. This matters at scale — e.g. a whole class opening an assessment
 * together would otherwise have 500 timers ticking in near-lockstep every 10
 * minutes, each sending a beat regardless of whether it's redundant.
 *
 * On top of that, the tick itself is jittered (BEAT_MS ± JITTER_MS, re-rolled
 * every cycle — see nextDelay) so even the idle tabs that do need a beat don't
 * all land on the same second. Between the skip-check and the jitter, a
 * synchronized class start turns into scattered, mostly-suppressed traffic
 * instead of a recurring 500-request burst every 10 minutes.
 *
 * Uses raw fetch, never the axios instance, and this is deliberate: axios's
 * response interceptor wipes localStorage and redirects to /login on any 401
 * (see api.service.ts), so a timer beat racing token expiry would throw a
 * reading student out to the login screen. Every failure here is swallowed —
 * presence must never disturb a user.
 */
export function usePresenceHeartbeat(isAuthenticated: boolean): void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

    const beat = () => {
      // Someone else (an action-triggered ping) already covered this window —
      // sending again would just be a no-op UPDATE on the backend, so skip it.
      if (Date.now() - getLastHeartbeatAt() < HEARTBEAT_THROTTLE_MS) return;
      const token = localStorage.getItem('access_token');
      if (!token) return;
      markHeartbeatSent();
      void fetch(`${API_BASE_URL}${API_ENDPOINTS.LOGIN_ACTIVITY.HEARTBEAT}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        keepalive: true,
      }).catch(() => {
        // Best-effort: allow a retry sooner if the ping failed.
        clearHeartbeatSent();
      });
    };
    const leave = () => send(API_ENDPOINTS.LOGIN_ACTIVITY.LEAVE);

    // A self-rescheduling setTimeout rather than setInterval: each cycle picks
    // a fresh random delay (see nextDelay), so the tick keeps drifting instead
    // of settling into a fixed period.
    const scheduleNext = () => {
      timerRef.current = setTimeout(() => {
        beat();
        scheduleNext();
      }, nextDelay());
    };
    const startTimer = () => {
      if (timerRef.current === null) {
        scheduleNext();
      }
    };
    const stopTimer = () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
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
