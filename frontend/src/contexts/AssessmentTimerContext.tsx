'use client';

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  useCallback,
  ReactNode,
} from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import { Loader, Text } from '@mantine/core';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { erDiagramService } from '@/services/er-diagram.service';

/**
 * A pre-finalize hook a mounted workspace registers so the finalize sequence can flush
 * its pending work first. It may return a staged uploaded image to include in the
 * end-of-assessment capture (uploads aren't persisted server-side as drafts).
 */
export type PreFinalizeHook = () => Promise<
  { imageQuestionId?: number; image?: File } | void
>;

interface AssessmentTimerContextValue {
  /** True only when the active session has a deadline (timed assessment). */
  hasTimer: boolean;
  /** Milliseconds remaining until the deadline (clamped at 0). */
  remainingMs: number;
  /** Display is frozen while a query runs. */
  isPaused: boolean;
  /** True while the end-of-assessment save+submit sequence is running. */
  isFinalizing: boolean;
  /** Freeze the displayed countdown (call when a query starts). */
  pause: () => void;
  /**
   * Unfreeze the countdown (call when the query response is back). Pass the credited
   * end_time from the response to resume immediately with no extra request; omit it (or
   * pass null/undefined, e.g. on error) to re-fetch the authoritative end_time instead.
   */
  resume: (newEndTimeIso?: string | null) => void;
  /**
   * Register a callback run right before finalize (timer end or manual submit); returns
   * an unregister fn. Lets a mounted ER workspace flush its draft and hand back a staged
   * uploaded image to capture.
   */
  registerPreFinalize: (fn: PreFinalizeHook) => () => void;
  /** Save any pending ER work, finalize the assessment, and navigate away. */
  finalizeWithSave: () => Promise<void>;
}

// Safe default so the shared workspaces can call pause()/resume() even when rendered
// outside an assessment (practice / staff) — there, the timer simply doesn't exist.
const DEFAULT: AssessmentTimerContextValue = {
  hasTimer: false,
  remainingMs: 0,
  isPaused: false,
  isFinalizing: false,
  pause: () => {},
  resume: () => {},
  registerPreFinalize: () => () => {},
  finalizeWithSave: async () => {},
};

const AssessmentTimerContext = createContext<AssessmentTimerContextValue>(DEFAULT);

export function useAssessmentTimer(): AssessmentTimerContextValue {
  return useContext(AssessmentTimerContext);
}

export function AssessmentTimerProvider({
  assessmentId,
  children,
}: {
  assessmentId: number;
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();

  // Deadline as epoch ms; null = untimed / not loaded.
  const [deadline, setDeadline] = useState<number | null>(null);
  const [remainingMs, setRemainingMs] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const submittingRef = useRef(false);
  // Workspaces register a flush-and-contribute callback here; run right before finalize.
  const preFinalizeHooksRef = useRef<Set<PreFinalizeHook>>(new Set());
  const registerPreFinalize = useCallback((fn: PreFinalizeHook) => {
    preFinalizeHooksRef.current.add(fn);
    return () => {
      preFinalizeHooksRef.current.delete(fn);
    };
  }, []);
  // The gateway hard cap rarely changes, and the query-run "resume" fast path only carries
  // the credited end_time — so remember the cap here and re-fold it in on every apply.
  const hardDeadlineRef = useRef<string | null>(null);

  // The effective deadline is the EARLIER of the personal timer (end_time, which query
  // credit pushes forward) and the Timing-Gateway class-group window cap (hard_deadline,
  // which never moves). This is the client half of requirement #5 — the student's screen
  // ends at whichever comes first. The backend enforces the same rule authoritatively.
  const applyEndTime = useCallback(
    (endTimeIso: string | null | undefined, hardDeadlineIso?: string | null) => {
      const candidates: number[] = [];
      if (endTimeIso) candidates.push(new Date(endTimeIso).getTime());
      if (hardDeadlineIso) candidates.push(new Date(hardDeadlineIso).getTime());
      if (candidates.length > 0) {
        const ms = Math.min(...candidates);
        setDeadline(ms);
        setRemainingMs(Math.max(0, ms - Date.now()));
      } else {
        setDeadline(null);
      }
    },
    []
  );

  // Sync the session's end_time on mount and on every in-assessment navigation.
  // The provider is mounted by the shared [id] layout, which persists across client
  // navigations between the landing, overview and item pages — so re-reading on pathname
  // change is what picks up the freshly-created session right after the student clicks
  // Join (landing -> overview), which a one-time mount fetch would miss.
  useEffect(() => {
    let cancelled = false;
    studentAssessmentService
      .getSession(assessmentId)
      .then((session) => {
        if (!cancelled) {
          hardDeadlineRef.current = session.hard_deadline ?? null;
          applyEndTime(session.end_time, hardDeadlineRef.current);
        }
      })
      .catch(() => {
        // No active session (not joined yet, or already submitted) — no timer.
      });
    return () => {
      cancelled = true;
    };
  }, [assessmentId, applyEndTime, pathname]);

  // Save any pending ER work, then finalize. Shared by the time's-up auto-submit and the
  // manual "End & Submit" button so both capture unsubmitted diagrams. The order matters:
  // (1) freeze the countdown, (2) let mounted workspaces flush their pending work (and hand
  // back a staged uploaded image), (3) grade the changed drafts via the trusted
  // finalize-pending endpoint (not blocked by the deadline; it credits time), (4) finalize
  // so scores are computed with the fresh grades. Every step is best-effort — a failure
  // still finalizes and navigates so the student is never stranded on a dead screen.
  const finalizeWithSave = useCallback(async () => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setIsFinalizing(true);
    setIsPaused(true);
    try {
      let imageQuestionId: number | undefined;
      let image: File | undefined;
      for (const hook of Array.from(preFinalizeHooksRef.current)) {
        try {
          const res = await hook();
          if (res?.image && res.imageQuestionId !== undefined) {
            imageQuestionId = res.imageQuestionId;
            image = res.image;
          }
        } catch {
          // A failed flush must never block finalize.
        }
      }
      try {
        await erDiagramService.finalizePending(assessmentId, { imageQuestionId, image });
      } catch {
        // End-of-assessment capture is best-effort; still finalize below.
      }
      try {
        await studentAssessmentService.submit(assessmentId);
      } catch {
        // Backend may have already finalized it via lazy expiration — ignore.
      }
    } finally {
      router.push('/student/assessments');
    }
  }, [assessmentId, router]);

  // Fired once when the countdown hits zero. The backend enforces the real deadline lazily;
  // this is the UX half that ends the attempt on the student's screen.
  const autoSubmit = useCallback(() => {
    if (submittingRef.current) return;
    notifications.show({
      title: "Time's up",
      message: 'Your assessment time has ended and has been submitted automatically.',
      color: 'red',
    });
    void finalizeWithSave();
  }, [finalizeWithSave]);

  // Tick once per second while running (not paused, deadline known).
  useEffect(() => {
    if (deadline === null || isPaused) return;

    const tick = () => {
      const left = Math.max(0, deadline - Date.now());
      setRemainingMs(left);
      if (left <= 0) autoSubmit();
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [deadline, isPaused, autoSubmit]);

  const pause = useCallback(() => {
    if (deadline === null) return;
    setIsPaused(true);
  }, [deadline]);

  const resume = useCallback(
    (newEndTimeIso?: string | null) => {
      if (deadline === null) {
        setIsPaused(false);
        return;
      }
      if (newEndTimeIso) {
        // Fast path: the run response already carried the credited end_time — no extra
        // request. Re-fold the remembered gateway cap so the window end still bounds it.
        applyEndTime(newEndTimeIso, hardDeadlineRef.current);
        setIsPaused(false);
        return;
      }
      // Fallback (e.g. error, or a path that doesn't return end_time): re-fetch the
      // authoritative end_time, then unfreeze so the countdown continues from it.
      studentAssessmentService
        .getSession(assessmentId)
        .then((session) => {
          hardDeadlineRef.current = session.hard_deadline ?? null;
          applyEndTime(session.end_time, hardDeadlineRef.current);
        })
        .catch(() => {})
        .finally(() => setIsPaused(false));
    },
    [assessmentId, deadline, applyEndTime]
  );

  const value: AssessmentTimerContextValue = {
    hasTimer: deadline !== null,
    remainingMs,
    isPaused,
    isFinalizing,
    pause,
    resume,
    registerPreFinalize,
    finalizeWithSave,
  };

  return (
    <AssessmentTimerContext.Provider value={value}>
      {children}
      {isFinalizing && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 10000,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
            background: 'rgba(0, 0, 0, 0.6)',
          }}
        >
          <Loader size="lg" color="white" />
          <Text c="white" fw={600} size="lg">
            Saving your work…
          </Text>
        </div>
      )}
    </AssessmentTimerContext.Provider>
  );
}
