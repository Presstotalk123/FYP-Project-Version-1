'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { erAnalyticsService } from '@/services/er-analytics.service';
import { queryKeys } from '@/services/query-keys';

const METRIC_LABEL: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-muted)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const pct = (v: number | null): string => (v == null ? '—' : `${v}%`);
const day = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleDateString() : '—';

export function ErdAnalyticsTab() {
  const router = useRouter();
  const [classGroup, setClassGroup] = useState('');

  const groupsQuery = useQuery({
    queryKey: ['erClassGroups'],
    queryFn: () => erAnalyticsService.classGroups(),
  });
  const engagementQuery = useQuery({
    queryKey: queryKeys.erdEngagement(classGroup || null),
    queryFn: () => erAnalyticsService.studentEngagement(classGroup || undefined),
    placeholderData: (prev) => prev,
  });

  const data = engagementQuery.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h2>ERD analytics</h2>
          <p>Per-student engagement across every ERD question.</p>
        </div>
        <select
          className="da-select"
          value={classGroup}
          onChange={(e) => setClassGroup(e.target.value)}
          aria-label="Class group"
        >
          <option value="">All classes</option>
          {(groupsQuery.data ?? []).map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
        {/* Rubric dimensions / failing checks live on the class overview page —
            not duplicated here. */}
        <button className="btn btn-secondary" onClick={() => router.push('/admin/er-analytics')}>
          Class overview
        </button>
      </div>

      {engagementQuery.isLoading ? (
        <div className="loading-center">
          <div className="spinner" />
          <span>Loading ERD analytics…</span>
        </div>
      ) : engagementQuery.error ? (
        <div className="da-alert alert-error" role="alert">
          <strong>Error</strong>
          <span>Failed to load ERD analytics.</span>
        </div>
      ) : data && (
        <div style={{ opacity: engagementQuery.isFetching ? 0.6 : 1 }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
              gap: 16,
              marginBottom: 18,
            }}
          >
            <article className="card metric" style={{ borderLeft: '3px solid var(--brand-lilac)' }}>
              <div>
                <span style={METRIC_LABEL}>Submissions</span>
                <strong>{data.totals.practice_submissions + data.totals.assessment_submissions}</strong>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {data.totals.practice_submissions} practice · {data.totals.assessment_submissions} assessment
                </span>
              </div>
              <span className="badge brand-badge">ERD</span>
            </article>
            <article className="card metric" style={{ borderLeft: '3px solid var(--success)' }}>
              <div>
                <span style={METRIC_LABEL}>Students Engaged</span>
                <strong>{data.totals.students_engaged}</strong>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  of {data.totals.registered_students} registered
                </span>
              </div>
              <span className="badge badge-success">Students</span>
            </article>
            <article className="card metric" style={{ borderLeft: '3px solid var(--info)' }}>
              <div>
                <span style={METRIC_LABEL}>Avg Best Score</span>
                <strong>{pct(data.totals.avg_best_percent)}</strong>
              </div>
              <span className="badge badge-info">Score</span>
            </article>
            <article className="card metric" style={{ borderLeft: '3px solid var(--warning)' }}>
              <div>
                <span style={METRIC_LABEL}>Baloo Queries</span>
                <strong>{data.totals.baloo_queries}</strong>
              </div>
              <span className="badge badge-warn">Baloo</span>
            </article>
          </div>

          <h3 style={{ marginBottom: 8 }}>Students</h3>
          {data.students.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>No ERD activity recorded yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Class</th>
                    <th style={{ textAlign: 'right' }}>Practice subs</th>
                    <th style={{ textAlign: 'right' }}>Questions tried</th>
                    <th style={{ textAlign: 'right' }}>Practice best</th>
                    <th style={{ textAlign: 'right' }}>Practice avg</th>
                    <th style={{ textAlign: 'right' }}>Baloo queries</th>
                    <th>First activity</th>
                  </tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.user_id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{s.name || s.email}</div>
                        {s.name && (
                          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.email}</div>
                        )}
                      </td>
                      <td>{s.class_group || '—'}</td>
                      <td style={{ textAlign: 'right' }}>{s.practice_submissions}</td>
                      <td style={{ textAlign: 'right' }}>{s.distinct_practice_questions}</td>
                      <td style={{ textAlign: 'right' }}>{pct(s.practice_best_percent)}</td>
                      <td style={{ textAlign: 'right' }}>{pct(s.practice_avg_percent)}</td>
                      <td style={{ textAlign: 'right' }}>{s.baloo_queries}</td>
                      <td>{day(s.first_activity_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </>
  );
}
