'use client';

import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { assessmentService } from '@/services/assessment.service';
import { queryKeys } from '@/services/query-keys';
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

  // Everything on this tab rides on the analytics summary: it carries the
  // platform-wide question/attempt totals (bank questions; student attempts,
  // SQL + ERD) alongside registered/signed-in, and it is served from
  // /assessments because /whitelist is admin-only while this dashboard is
  // staff + admin. Same key as the Assessments tab, so whichever tab is opened
  // first pays for the fetch.
  const summaryQuery = useQuery({
    queryKey: queryKeys.assessmentAnalyticsSummary,
    queryFn: () => assessmentService.getAnalyticsSummary(),
  });

  if (summaryQuery.isLoading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
        <span>Loading stats…</span>
      </div>
    );
  }

  const s = summaryQuery.data;
  const totalQuestions = (s?.total_sql_questions ?? 0) + (s?.total_erd_questions ?? 0);
  const totalAttempts = (s?.total_sql_attempts ?? 0) + (s?.total_erd_submissions ?? 0);
  const registered = s?.platform_registered;
  const signedIn = s?.platform_signed_in;

  return (
    <>
      <ActiveUsersCard />

      <div className="grid-3" style={{ marginBottom: 18 }}>
        <article className="card metric" style={{ borderLeft: '3px solid var(--brand-lilac)' }}>
          <div>
            <span style={METRIC_LABEL}>Total Questions</span>
            <strong>{totalQuestions}</strong>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {s?.total_sql_questions ?? 0} SQL · {s?.total_erd_questions ?? 0} ERD
            </span>
          </div>
        </article>

        <article className="card metric" style={{ borderLeft: '3px solid var(--success)' }}>
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
        </article>

        <article className="card metric" style={{ borderLeft: '3px solid var(--warning)' }}>
          <div>
            <span style={METRIC_LABEL}>Total Attempts</span>
            <strong>{totalAttempts}</strong>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {s?.total_sql_attempts ?? 0} SQL · {s?.total_erd_submissions ?? 0} ERD
            </span>
          </div>
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
