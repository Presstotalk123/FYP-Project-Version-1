import { useCallback, useEffect, useRef, useState } from 'react';

interface Options {
  /** Attempts with no cooldown (default 3). */
  freeLimit?: number;
  /** Attempts through the middle tier (default 6). Beyond this uses tier2Cooldown. */
  tier1Limit?: number;
  /** Seconds of cooldown for the middle tier (default 10). */
  tier1Cooldown?: number;
  /** Seconds of cooldown beyond tier1Limit (default 20). */
  tier2Cooldown?: number;
  /** sessionStorage key — scopes the counter to a resource (question/lab). */
  storageKey: string;
}

interface Persisted {
  attempts: number;
  cooldownUntil: number; // epoch ms; 0 = no active cooldown
}

function readState(key: string): Persisted {
  if (typeof window === 'undefined') return { attempts: 0, cooldownUntil: 0 };
  try {
    const raw = window.sessionStorage.getItem(key);
    if (raw) return JSON.parse(raw) as Persisted;
  } catch {
    /* ignore corrupt/unavailable storage */
  }
  return { attempts: 0, cooldownUntil: 0 };
}

/**
 * Progressive Run cooldown. Tracks how many times a student has run a query for
 * a given resource and disables Run for an increasing duration:
 *   attempts <= freeLimit  -> 0s
 *   attempts <= tier1Limit -> tier1Cooldown
 *   otherwise              -> tier2Cooldown
 *
 * The count and any in-progress cooldown persist in sessionStorage (keyed by
 * storageKey), so navigating away or reloading resumes the same state. The
 * remaining time is tracked internally only to know when to re-enable — it is
 * intentionally not exposed for display.
 */
export function useRunCooldown({
  freeLimit = 3,
  tier1Limit = 6,
  tier1Cooldown = 10,
  tier2Cooldown = 20,
  storageKey,
}: Options) {
  const attemptsRef = useRef(0);
  const [remaining, setRemaining] = useState(0); // seconds left; internal, not displayed
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Refs so the stable callbacks always read the latest values (tasks load async; key can change).
  const cfgRef = useRef({ freeLimit, tier1Limit, tier1Cooldown, tier2Cooldown });
  cfgRef.current = { freeLimit, tier1Limit, tier1Cooldown, tier2Cooldown };
  const keyRef = useRef(storageKey);
  keyRef.current = storageKey;

  const clear = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  const startCountdown = useCallback((cooldownUntil: number) => {
    clear();
    const tick = () => {
      const secs = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
      setRemaining(secs);
      if (secs <= 0) clear();
    };
    tick(); // set immediately
    intervalRef.current = setInterval(tick, 1000);
  }, []);

  // Hydrate on mount / when the resource key changes.
  useEffect(() => {
    const s = readState(keyRef.current);
    attemptsRef.current = s.attempts;
    if (s.cooldownUntil > Date.now()) startCountdown(s.cooldownUntil);
    else setRemaining(0);
    return () => clear();
  }, [storageKey, startCountdown]);

  // Call this AFTER a Run request completes (in the finally block).
  const registerRunComplete = useCallback(() => {
    attemptsRef.current += 1;
    const n = attemptsRef.current;
    const { freeLimit, tier1Limit, tier1Cooldown, tier2Cooldown } = cfgRef.current;
    const secs = n <= freeLimit ? 0 : n <= tier1Limit ? tier1Cooldown : tier2Cooldown;
    const cooldownUntil = secs > 0 ? Date.now() + secs * 1000 : 0;
    try {
      window.sessionStorage.setItem(
        keyRef.current,
        JSON.stringify({ attempts: n, cooldownUntil }),
      );
    } catch {
      /* ignore unavailable storage */
    }
    if (secs > 0) startCountdown(cooldownUntil);
  }, [startCountdown]);

  return { isCoolingDown: remaining > 0, registerRunComplete };
}
