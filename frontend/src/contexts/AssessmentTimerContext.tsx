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
import { studentAssessmentService } from '@/services/studentAssessment.service';

interface AssessmentTimerContextValue {
  /** True only when the active session has a deadline (timed assessment). */
  hasTimer: boolean;
  /** Milliseconds remaining until the deadline (clamped at 0). */
  remainingMs: number;
  /** Display is frozen while a query runs. */
  isPaused: boolean;
  /** Freeze the displayed countdown (call when a query starts). */
  pause: () => void;
  /**
   * Unfreeze the countdown (call when the query response is back). Pass the credited
   * end_time from the response to resume immediately with no extra request; omit it (or
   * pass null/undefined, e.g. on error) to re-fetch the authoritative end_time instead.
   */
  resume: (newEndTimeIso?: string | null) => void;
}

// Safe default so the shared workspaces can call pause()/resume() even when rendered
// outside an assessment (practice / staff) — there, the timer simply doesn't exist.
const DEFAULT: AssessmentTimerContextValue = {
  hasTimer: false,
  remainingMs: 0,
  isPaused: false,
  pause: () => {},
  resume: () => {},
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
  const submittingRef = useRef(false);
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

  // Auto-submit once when time runs out. The backend enforces the real deadline lazily;
  // this is the UX half that ends the attempt on the student's screen.
  const autoSubmit = useCallback(async () => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    notifications.show({
      title: "Time's up",
      message: 'Your assessment time has ended and has been submitted automatically.',
      color: 'red',
    });
    try {
      await studentAssessmentService.submit(assessmentId);
    } catch {
      // Backend may have already finalized it via lazy expiration — ignore.
    } finally {
      router.push('/student/assessments');
    }
  }, [assessmentId, router]);

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
    pause,
    resume,
  };

  return (
    <AssessmentTimerContext.Provider value={value}>
      {children}
    </AssessmentTimerContext.Provider>
  );
}
