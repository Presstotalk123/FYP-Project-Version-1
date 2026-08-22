'use client';

import { useEffect } from 'react';

/**
 * Blocks browser history traversal — back AND forward (button, swipe/gesture,
 * Alt+Left/Right, mouse back/forward buttons) — while `enabled`. The History API's
 * `popstate` event fires the same way regardless of direction, so a single handler
 * covers both: it re-pushes a guard entry for the current URL on mount and on every
 * `popstate`. Each `pushState` call also discards any forward entries beyond it, so
 * once this is active the browser's Forward button has nothing to go to and stays
 * disabled — there's no separate "forward" case to special-case.
 *
 * Used on assessment question workspaces so a stray back/forward press can't pull a
 * student out mid-attempt; students still leave via the explicit "Save and Exit"
 * controls.
 *
 * Note: this only guards in-app SPA history traversal — it can't stop a full page
 * unload (closing the tab, typing a new URL), which is unrelated to `popstate`.
 */
export function useBlockBrowserBack(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;

    window.history.pushState(null, '', window.location.href);
    const handlePopState = () => {
      window.history.pushState(null, '', window.location.href);
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [enabled]);
}
