'use client';

import { useEffect } from 'react';

/**
 * Shows the browser's native "leave site?" confirmation (tab close, refresh,
 * typing a new URL, closing the window) while `enabled`. This is the full-page-
 * unload counterpart to [[use-block-browser-back]] — that hook can only guard
 * in-app SPA back/forward navigation via `popstate`; it explicitly can't stop a
 * real unload, which is what this hook is for.
 *
 * Browsers ignore any custom message and show their own generic wording (e.g.
 * "Leave site? Changes you made may not be saved"), so the `beforeunload`
 * listener just needs to call `preventDefault()` / set `returnValue` to trigger
 * that native prompt — there's no way to display our own "progress may be lost"
 * copy in the dialog itself.
 */
export function useWarnBeforeUnload(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [enabled]);
}
