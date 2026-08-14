'use client';

import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { questionService } from '@/services/question.service';
import { assessmentService } from '@/services/assessment.service';
import { queryKeys } from '@/services/query-keys';
import api from '@/services/api.service';
import { ActiveUsersCard } from '@/components/admin/ActiveUsersCard';

const METRIC_LABEL: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-muted)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

export function OverviewTab() {
  const router = useRouter();

  const questionsQuery = useQuery({
    queryKey: queryKeys.questions,
    queryFn: () => questionService.getQuestions(),
  });
  const attemptsQuery = useQuery({
    queryKey: queryKeys.attempts,
    queryFn: async () => (await api.get('/attempts')).data as unknown[],
  });
  // Registered/signed-in ride on the analytics summary because /whitelist is admin-only
  // while this dashboard is staff + admin. Same key as the Assessments tab, so whichever
  // tab is opened first pays for the fetch.
  const summaryQuery = useQuery({
    queryKey: queryKeys.assessmentAnalyticsSummary,
    queryFn: () => assessmentService.getAnalyticsSummary(),
  });

  if (questionsQuery.isLoading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
        <span>Loading stats…</span>
      </div>
    );
  }

  const totalQuestions = questionsQuery.data?.length ?? 0;
  const totalAttempts = attemptsQuery.data?.length ?? 0;
  const registered = summaryQuery.data?.platform_registered;
  const signedIn = summaryQuery.data?.platform_signed_in;

  return (
    <>
      <ActiveUsersCard />

      <div className="grid-3" style={{ marginBottom: 18 }}>
        <article className="card metric">
          <div>
            <span style={METRIC_LABEL}>Total Questions</span>
            <strong>{totalQuestions}</strong>
          </div>
          <span className="badge brand-badge">SQL</span>
        </article>

        <article className="card metric">
          <div>
            <span style={METRIC_LABEL}>Registered Students</span>
            <strong>{registered ?? '—'}</strong>
            {/* A failed summary must degrade to a dash, never blank the whole tab or
                sit on "loading…" forever. */}
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {summaryQuery.error
                ? 'unavailable'
                : signedIn == null
                  ? 'loading…'
                  : `${signedIn} signed in`}
            </span>
          </div>
          <span className="badge badge-success">Students</span>
        </article>

        <article className="card metric">
          <div>
            <span style={METRIC_LABEL}>Total Attempts</span>
            <strong>{totalAttempts}</strong>
          </div>
          <span className="badge badge-warn">Attempts</span>
        </article>
      </div>

      <article className="card">
        <h3 style={{ marginBottom: 14 }}>Quick Actions</h3>
        <div className="button-row">
          <button className="btn btn-primary" onClick={() => router.push('/admin/questions')}>
            Manage Questions
          </button>
          <button className="btn btn-secondary" onClick={() => router.push('/admin/questions/new')}>
            Create New Question
          </button>
          <button className="btn btn-secondary" onClick={() => router.push('/admin/labs')}>
            Manage Labs
          </button>
        </div>
      </article>
    </>
  );
}
