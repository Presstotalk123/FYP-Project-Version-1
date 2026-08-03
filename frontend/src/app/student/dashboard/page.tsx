'use client';

import { useMemo } from 'react';
import type { CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { questionService } from '@/services/question.service';
import { erDiagramService } from '@/services/er-diagram.service';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { queryKeys } from '@/services/query-keys';

const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
  </svg>
);

const metricLabelStyle: CSSProperties = {
  fontSize: 13,
  color: 'var(--text-muted)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

// Weighted scores are 0-100; treat a pass mark of 50 for the badge colour.
const scoreBadgeClass = (score: number) => (score >= 50 ? 'badge-success' : 'badge-warn');

export default function StudentDashboardOverview() {
  // Session-cached (see providers.tsx). Counts are tiny {total, attempted} payloads;
  // the totals are computed once and cached server-side (see /questions/count).
  const sqlCountQuery = useQuery({
    queryKey: queryKeys.studentQuestionCount,
    queryFn: () => questionService.getCount(),
  });
  const erdCountQuery = useQuery({
    queryKey: queryKeys.studentErdCount,
    queryFn: () => erDiagramService.getQuestionCount(),
  });
  const assessmentsQuery = useQuery({
    queryKey: queryKeys.studentAssessments,
    queryFn: () => studentAssessmentService.list(),
  });

  const sql = sqlCountQuery.data ?? { total: 0, attempted: 0 };
  const erd = erdCountQuery.data ?? { total: 0, attempted: 0 };

  // Only assessments the student has submitted, newest first.
  const attempted = useMemo(() => {
    const list = assessmentsQuery.data ?? [];
    return list
      .filter((a) => a.attempt_complete)
      .sort((a, b) => {
        const at = a.submitted_at ? new Date(a.submitted_at).getTime() : 0;
        const bt = b.submitted_at ? new Date(b.submitted_at).getTime() : 0;
        return bt - at;
      });
  }, [assessmentsQuery.data]);

  const recent = attempted[0] ?? null;

  const loading = sqlCountQuery.isLoading || erdCountQuery.isLoading || assessmentsQuery.isLoading;
  const loadError = sqlCountQuery.error || erdCountQuery.error || assessmentsQuery.error;
  const error = loadError
    ? ((loadError as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load dashboard')
    : null;
  const refreshing = sqlCountQuery.isFetching || erdCountQuery.isFetching || assessmentsQuery.isFetching;
  const refresh = () => {
    sqlCountQuery.refetch();
    erdCountQuery.refetch();
    assessmentsQuery.refetch();
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        {/* Header */}
        <div className="page-head">
          <div>
            <h2>Dashboard</h2>
            <p>Your practice progress and assessment results at a glance.</p>
          </div>
          <div className="button-row">
            <button className="btn btn-secondary" onClick={refresh} disabled={refreshing} title="Reload latest data from the server">
              <IconRefresh />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading dashboard…</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {!loading && !error && (
          <>
            {/* Metric cards */}
            <div className="grid-3" style={{ marginBottom: 18 }}>
              <article className="card metric">
                <div>
                  <span style={metricLabelStyle}>SQL Questions Done</span>
                  <strong>{sql.attempted} / {sql.total}</strong>
                </div>
                <span className="badge brand-badge">SQL</span>
              </article>

              <article className="card metric">
                <div>
                  <span style={metricLabelStyle}>ERD Questions Done</span>
                  <strong>{erd.attempted} / {erd.total}</strong>
                </div>
                <span className="badge brand-badge">ERD</span>
              </article>

              <article className="card metric">
                <div>
                  <span style={metricLabelStyle}>Recent Assessment</span>
                  {recent ? (
                    <>
                      <strong style={{ fontSize: 22 }}>
                        {recent.weighted_score != null ? `${Math.round(recent.weighted_score)}%` : '—'}
                      </strong>
                      <span
                        style={{ fontSize: 13, color: 'var(--text-muted)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}
                        title={recent.title}
                      >
                        {recent.title}
                      </span>
                    </>
                  ) : (
                    <strong style={{ fontSize: 22 }}>—</strong>
                  )}
                </div>
                {recent && recent.weighted_score == null && (
                  <span className="badge neutral">Awaiting results</span>
                )}
              </article>
            </div>

            {/* Assessments attempted */}
            <article className="card">
              <h3 style={{ marginBottom: 14 }}>Assessments Attempted</h3>
              {attempted.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>No assessments attempted yet.</p>
              ) : (
                <div className="table-wrap">
                  <table className="da-table">
                    <thead>
                      <tr>
                        <th>Assessment</th>
                        <th>Submitted</th>
                        <th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attempted.map((a) => (
                        <tr key={a.id}>
                          <td style={{ fontWeight: 600 }}>{a.title}</td>
                          <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                            {a.submitted_at ? new Date(a.submitted_at).toLocaleDateString() : '—'}
                          </td>
                          <td>
                            {a.weighted_score != null ? (
                              <span className={`badge ${scoreBadgeClass(a.weighted_score)}`}>
                                {Math.round(a.weighted_score)}%
                              </span>
                            ) : (
                              <span className="badge neutral">Pending release</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </article>
          </>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
