"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * "Don't remind me again" for the ER-diagram focus-mode guide.
 *
 * Kept in localStorage, per user, like the colour-scheme preference: it is a
 * UI nicety, not part of the student's work, so it does not need to follow
 * them across devices the way the diagram draft does. Closing the guide with
 * "Got it" (or the X) is deliberately NOT remembered — only the explicit
 * "Don't remind me again" button is — so a student who skims past it once
 * still gets it next time.
 */
export const erdGuideDismissedKey = (userId: number | null): string =>
  `erd-guide-dismissed-u${userId ?? "anon"}`;

const readDismissed = (userId: number | null): boolean => {
  try {
    return window.localStorage.getItem(erdGuideDismissedKey(userId)) === "1";
  } catch {
    return false;
  }
};

// localStorage is an external store, so it is read through
// useSyncExternalStore: the server snapshot is "not dismissed", the client
// snapshot is the real value, and same-tab writes notify through `emit`
// (the browser only fires `storage` events for writes made by OTHER tabs).
const listeners = new Set<() => void>();

const subscribe = (onChange: () => void): (() => void) => {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
};

const emit = () => {
  listeners.forEach((listener) => listener());
};

const getServerSnapshot = () => false;

export type ErdGuideDismissal = {
  dismissed: boolean;
  dismissForever: () => void;
};

export function useErdGuideDismissed(userId: number | null): ErdGuideDismissal {
  const dismissed = useSyncExternalStore(
    subscribe,
    () => readDismissed(userId),
    getServerSnapshot,
  );

  const dismissForever = useCallback(() => {
    try {
      window.localStorage.setItem(erdGuideDismissedKey(userId), "1");
    } catch {
      // Storage unavailable (private mode / quota): nothing is remembered, so
      // the guide simply comes back next time — the honest outcome.
    }
    emit();
  }, [userId]);

  return { dismissed, dismissForever };
}
