"use client";

import { useGuideDismissed, type GuideDismissal } from "@/hooks/use-guide-dismissed";

/** Backend allow-list key for the ER-diagram focus-mode guide (services/user_preferences.py). */
export const ERD_GUIDE_DISMISSED_KEY = "erd_guide_dismissed";

/** "Don't remind me again" for the ER-diagram guide — see useGuideDismissed. */
export function useErdGuideDismissed(userId: number | null): GuideDismissal {
  return useGuideDismissed(ERD_GUIDE_DISMISSED_KEY, userId);
}
