'use client';

import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { reportService } from '@/services/report.service';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { queryKeys } from '@/services/query-keys';

const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
  </svg>
);

// One metric card. `label` sits above a big count; `badge` is the type tag on the right.
function MetricCard({ label, value, badgeText, badgeClass }: {
  label: string;
  value: number;
  badgeText: string;
  badgeClass: string;
}) {
  return (
    <article className="card metric">
      <div>
        <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {label}
        </span>
        <strong>{value}</strong>
      </div>
      <span className={`badge ${badgeClass}`}>{badgeText}</span>
    </article>
  );
}

export default function StudentReportPage() {
  // Practice-completion counts (server aggregated).
  const summaryQuery = useQuery({
    queryKey: queryKeys.studentReportSummary,
    queryFn: () => reportService.getSummary(),
  });
  // Assessment scores reuse the existing student assessments list; each item
  // already carries its weighted_score. We show only submitted attempts.
  const assessmentsQuery = useQuery({
    queryKey: queryKeys.studentAssessments,
    queryFn: () => studentAssessmentService.list(),
  });

  const summary = summaryQuery.data;
  const submitted = (assessmentsQuery.data ?? [])
    .filter((a) => a.attempt_complete)
    .sort((a, b) => {
      // Most recently submitted first; undated (edge case) sinks to the bottom.
      const ta = a.submitted_at ? new Date(a.submitted_at).getTime() : 0;
      const tb = b.submitted_at ? new Date(b.submitted_at).getTime() : 0;
      return tb - ta;
    });

  const loading = summaryQuery.isLoading || assessmentsQuery.isLoading;
  const loadError = summaryQuery.error || assessmentsQuery.error;
  const error = loadError
    ? ((loadError as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load your report')
    : null;
  const refreshing = summaryQuery.isFetching || assessmentsQuery.isFetching;
  const refresh = () => {
    summaryQuery.refetch();
    assessmentsQuery.refetch();
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>My Report</h2>
            <p>Your completed practice and your assessment results in one place.</p>
          </div>
          <div className="button-row">
            <button className="btn btn-secondary" onClick={refresh} disabled={refreshing} title="Reload latest data from the server">
              <IconRefresh />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {loading && (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading your report…</span>
          </div>
        )}

        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {!loading && !error && summary && (
          <>
            {/* Practice completion */}
            <h3 style={{ margin: '4px 0 12px' }}>Practice completed</h3>
            <div className="grid-3" style={{ marginBottom: 26 }}>
              <MetricCard
                label="SQL Questions"
                value={summary.sql_questions_completed}
                badgeText="SQL"
                badgeClass="badge-info"
              />
              <MetricCard
                label="ER Diagram Questions"
                value={summary.erd_questions_completed}
                badgeText="ERD"
                badgeClass="brand-badge"
              />
              <MetricCard
                label="Graph Labs"
                value={summary.graph_labs_completed}
                badgeText="Graph"
                badgeClass="brand-badge"
              />
              <MetricCard
                label="SQL Labs"
                value={summary.sql_labs_completed}
                badgeText="SQL Lab"
                badgeClass="badge-info"
              />
            </div>

            {/* Assessment results */}
            <h3 style={{ margin: '4px 0 12px' }}>Assessment scores</h3>
            {submitted.length === 0 ? (
              <div className="da-alert alert-info">
                <strong>No results yet</strong>
                <span>You haven&apos;t submitted any assessments yet. Scores appear here once you do.</span>
              </div>
            ) : (
              <div className="grid-3">
                {submitted.map((a) => (
                  <article key={a.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <h3 style={{
                      margin: 0, fontSize: 15,
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                    }}>
                      {a.title}
                    </h3>
                    <div style={{ marginTop: 'auto' }}>
                      {a.weighted_score !== null && a.weighted_score !== undefined ? (
                        <span
                          className={`badge ${a.weighted_score >= 50 ? 'badge-success' : 'badge-warn'}`}
                          style={{ fontSize: 15, padding: '4px 12px' }}
                        >
                          {a.weighted_score}%
                        </span>
                      ) : (
                        <span className="badge neutral">Pending results</span>
                      )}
                    </div>
                    {a.submitted_at && (
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        Submitted {new Date(a.submitted_at).toLocaleDateString()}
                      </span>
                    )}
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
