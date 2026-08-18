"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { userPreferencesService, type UserPreferences } from "@/services/user-preferences.service";

/**
 * "Don't remind me again" for an in-app guide, remembered on the student's
 * account so it follows them across devices.
 *
 * Two stores, server-first:
 *  - the server (GET/PUT /users/me/preferences) is the source of truth, keyed
 *    by `prefKey` (e.g. "erd_guide_dismissed"; the backend keeps the allow-list);
 *  - localStorage is a per-device cache of the same flag, so the answer is
 *    instant on the next visit and still there offline or if the request fails.
 *
 * Until the server has answered, the local copy decides. Once it has, the two
 * are reconciled: a server "dismissed" is cached locally, and a local
 * "dismissed" the server doesn't know about (a flag from before this feature,
 * or an earlier PUT that failed) is pushed up. Only the explicit "Don't remind
 * me again" button ever sets the flag — closing the guide does not.
 *
 * Adding a guide elsewhere (a SQL-workspace one, say) is a new `prefKey` here
 * plus one entry in the backend allow-list.
 */

/** Per-device cache key. `erd_guide_dismissed` + user 42 → `erd-guide-dismissed-u42`. */
export const guideDismissedLocalKey = (prefKey: string, userId: number | null): string =>
  `${prefKey.replace(/_/g, "-")}-u${userId ?? "anon"}`;

const readLocal = (localKey: string): boolean => {
  try {
    return window.localStorage.getItem(localKey) === "1";
  } catch {
    return false;
  }
};

const writeLocal = (localKey: string): void => {
  try {
    window.localStorage.setItem(localKey, "1");
  } catch {
    // Storage unavailable (private mode / quota): the server copy still holds
    // it, so nothing is lost — this device just re-fetches next time.
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

/** One cache entry per user, so a sign-out/sign-in in the same tab never reads
 *  the previous account's flags. */
export const userPreferencesQueryKey = (userId: number | null) => ["userPreferences", userId] as const;

export type GuideDismissal = {
  dismissed: boolean;
  dismissForever: () => void;
};

export function useGuideDismissed(prefKey: string, userId: number | null): GuideDismissal {
  const queryClient = useQueryClient();
  const queryKey = userPreferencesQueryKey(userId);
  const localKey = guideDismissedLocalKey(prefKey, userId);

  const prefs = useQuery({
    queryKey,
    queryFn: () => userPreferencesService.getMine(),
    enabled: userId !== null,
    // Preferences change only through this hook, which patches the cache
    // itself, so a fetch per page load is plenty.
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const localDismissed = useSyncExternalStore(
    subscribe,
    () => readLocal(localKey),
    getServerSnapshot,
  );

  const serverKnown = prefs.data !== undefined;
  const serverDismissed = serverKnown ? prefs.data[prefKey] === "1" : undefined;
  const dismissed = serverDismissed ?? localDismissed;

  const markDismissedInCache = useCallback(() => {
    queryClient.setQueryData<UserPreferences>(queryKey, (old) => ({ ...(old ?? {}), [prefKey]: "1" }));
  }, [queryClient, queryKey, prefKey]);

  // Reconcile the two stores once the server has answered (see the header
  // comment). Writing localStorage / calling the API from an effect is the
  // intended use of an effect: syncing React state out to external systems.
  useEffect(() => {
    if (!serverKnown || userId === null) return;
    if (serverDismissed && !localDismissed) {
      writeLocal(localKey);
      emit();
    } else if (!serverDismissed && localDismissed) {
      userPreferencesService
        .setMine(prefKey, "1")
        .then(markDismissedInCache)
        .catch(() => {
          // Left as-is: the local copy still applies on this device, and the
          // next page load will try again.
        });
    }
  }, [serverKnown, serverDismissed, localDismissed, userId, localKey, prefKey, markDismissedInCache]);

  const dismissForever = useCallback(() => {
    // Local first, so the choice takes effect immediately and survives a
    // failed request; then the account copy.
    writeLocal(localKey);
    emit();
    if (userId === null) return;
    markDismissedInCache();
    userPreferencesService.setMine(prefKey, "1").catch(() => {
      // Same story: this device remembers; the reconcile effect will push it
      // up next time the server is reachable.
    });
  }, [localKey, userId, prefKey, markDismissedInCache]);

  return { dismissed, dismissForever };
}
