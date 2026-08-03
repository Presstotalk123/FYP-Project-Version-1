'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useParams } from 'next/navigation';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { StudentAssessmentItemView } from '@/types/assessment.types';

interface AssessmentProgressContextValue {
  /** True only when rendered inside the student assessment-taking layout. */
  inAssessment: boolean;
  assessmentId: number | null;
  items: StudentAssessmentItemView[];
  /** Assessment-item id (not resource id) of the item currently on screen, from the route. */
  currentItemId: number | null;
  /** Assessment-item ids the student has submitted/executed a solution for this session. */
  attemptedIds: Set<number>;
  /** Marks the item currently on screen as attempted. No-op outside an assessment. */
  markAttempted: () => void;
}

// Safe default so the shared workspaces can call markAttempted() even when rendered
// outside an assessment (practice / staff) — there, the navigator simply doesn't render.
const DEFAULT: AssessmentProgressContextValue = {
  inAssessment: false,
  assessmentId: null,
  items: [],
  currentItemId: null,
  attemptedIds: new Set(),
  markAttempted: () => {},
};

const AssessmentProgressContext = createContext<AssessmentProgressContextValue>(DEFAULT);

export function useAssessmentProgress(): AssessmentProgressContextValue {
  return useContext(AssessmentProgressContext);
}

// Persisted per-assessment so the navigator survives a full page refresh (a client-side
// nav between items keeps the Context alive already; a hard reload does not). Session-
// scoped, not local: an assessment attempt is single-shot, so this shouldn't outlive the tab.
function progressStorageKey(assessmentId: number): string {
  return `assessment-progress:${assessmentId}`;
}

function loadAttemptedIds(assessmentId: number): Set<number> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = window.sessionStorage.getItem(progressStorageKey(assessmentId));
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? new Set(parsed) : new Set();
  } catch {
    return new Set();
  }
}

function saveAttemptedIds(assessmentId: number, ids: Set<number>): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(progressStorageKey(assessmentId), JSON.stringify(Array.from(ids)));
  } catch {
    // sessionStorage may throw (quota, private mode) — persistence is a nicety, never block on it.
  }
}

export function AssessmentProgressProvider({
  assessmentId,
  children,
}: {
  assessmentId: number;
  children: ReactNode;
}) {
  // Mounted once by the shared [id] layout, which persists across client navigations
  // between the overview and item pages — so reading itemId via useParams here tracks
  // the active item without needing the workspace pages to pass it down explicitly.
  const params = useParams<{ itemId?: string }>();
  const currentItemId = params?.itemId ? Number(params.itemId) : null;

  const [items, setItems] = useState<StudentAssessmentItemView[]>([]);
  const [attemptedIds, setAttemptedIds] = useState<Set<number>>(() => loadAttemptedIds(assessmentId));

  useEffect(() => {
    let cancelled = false;
    studentAssessmentService
      .getDetail(assessmentId)
      .then((detail) => {
        if (!cancelled) setItems(detail.items);
      })
      .catch(() => {
        // No active session yet (not joined) — the navigator just stays empty until then.
      });
    return () => {
      cancelled = true;
    };
  }, [assessmentId]);

  const markAttempted = useCallback(() => {
    if (currentItemId === null) return;
    setAttemptedIds((prev) => {
      if (prev.has(currentItemId)) return prev;
      const next = new Set(prev);
      next.add(currentItemId);
      saveAttemptedIds(assessmentId, next);
      return next;
    });
  }, [currentItemId, assessmentId]);

  const value: AssessmentProgressContextValue = {
    inAssessment: true,
    assessmentId,
    items,
    currentItemId,
    attemptedIds,
    markAttempted,
  };

  return (
    <AssessmentProgressContext.Provider value={value}>
      {children}
    </AssessmentProgressContext.Provider>
  );
}
