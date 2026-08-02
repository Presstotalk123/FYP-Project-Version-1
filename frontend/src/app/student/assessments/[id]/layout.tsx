'use client';

import { ReactNode } from 'react';
import { useParams } from 'next/navigation';
import { AssessmentTimerProvider } from '@/contexts/AssessmentTimerContext';
import { AssessmentProgressProvider } from '@/contexts/AssessmentProgressContext';

/**
 * Wraps the whole assessment subtree (overview + per-item workspaces) in a single
 * timer provider so the countdown survives navigation between full-page routes and
 * so pause/resume-on-Run works from inside the SQL/Lab workspaces.
 */
export default function StudentAssessmentLayout({ children }: { children: ReactNode }) {
  const params = useParams();
  const assessmentId = Number(params.id);

  return (
    <AssessmentTimerProvider assessmentId={assessmentId}>
      <AssessmentProgressProvider assessmentId={assessmentId}>
        {children}
      </AssessmentProgressProvider>
    </AssessmentTimerProvider>
  );
}
