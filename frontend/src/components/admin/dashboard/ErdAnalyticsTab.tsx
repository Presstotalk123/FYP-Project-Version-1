'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { erAnalyticsService } from '@/services/er-analytics.service';
import { queryKeys } from '@/services/query-keys';
import type { StudentEngagementRow } from '@/types/er-analytics.types';

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

type SortKey =
  | 'student'
  | 'class_group'
  | 'practice_submissions'
  | 'distinct_practice_questions'
  | 'practice_best_percent'
  | 'practice_avg_percent'
  | 'baloo_queries'
  | 'first_activity_at';

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: 'student', label: 'Student', numeric: false },
  { key: 'class_group', label: 'Class', numeric: false },
  { key: 'practice_submissions', label: 'Practice subs', numeric: true },
  { key: 'distinct_practice_questions', label: 'Questions tried', numeric: true },
  { key: 'practice_best_percent', label: 'Practice best', numeric: true },
  { key: 'practice_avg_percent', label: 'Practice avg', numeric: true },
  { key: 'baloo_queries', label: 'Baloo queries', numeric: true },
  { key: 'first_activity_at', label: 'First activity', numeric: false },
];

/** What each column actually sorts on. Students sort by display name (falling
 *  back to email); ISO timestamps compare fine as strings. */
const sortValue = (s: StudentEngagementRow, key: SortKey): string | number | null => {
  if (key === 'student') return (s.name || s.email).toLowerCase();
  // '' renders as '—' exactly like null, so it must sink with null too —
  // otherwise identical-looking rows sort to opposite ends.
  if (key === 'class_group') return s.class_group ? s.class_group.toLowerCase() : null;
  return s[key];
};

/** RFC-4180 quoting: wrap anything holding a comma, quote, or newline. */
const csvCell = (v: string | number | null): string => {
  const s = v == null ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/** The table as CSV, in the given (already sorted/filtered) order. Raw numbers,
 *  ISO dates — analysis-friendly rather than display-formatted. */
const studentsCsv = (rows: StudentEngagementRow[]): string => {
  const header = ['Name', 'Email', 'Class group', 'Practice submissions',
    'Questions tried', 'Practice best %', 'Practice avg %',
    'Baloo queries', 'First activity'];
  const lines = rows.map((s) => [
    s.name ?? '', s.email, s.class_group ?? '',
    s.practice_submissions, s.distinct_practice_questions,
    s.practice_best_percent ?? '', s.practice_avg_percent ?? '',
    s.baloo_queries, s.first_activity_at ?? '',
  ].map(csvCell).join(','));
  return [header.map(csvCell).join(','), ...lines].join('\r\n');
};

export function ErdAnalyticsTab() {
  const router = useRouter();
  const [classGroup, setClassGroup] = useState('');
  // Most practice first by default.
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({
    key: 'practice_submissions',
    dir: 'desc',
  });

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

  const toggleSort = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        // Text/date columns start alphabetical/oldest-first; counts start biggest-first.
        : { key, dir: COLUMNS.find((c) => c.key === key)?.numeric ? 'desc' : 'asc' },
    );
  };

  const sortedStudents = useMemo(() => {
    const rows = data?.students ?? [];
    const sign = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = sortValue(a, sort.key);
      const vb = sortValue(b, sort.key);
      // Missing values sink to the bottom whichever direction is active.
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'string' && typeof vb === 'string') {
        return sign * va.localeCompare(vb);
      }
      return sign * ((va as number) - (vb as number));
    });
  }, [data, sort]);

  return (
    <>
      <div className="page-head">
        <div>
          <h2>ERD Analytics</h2>
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
        <button
          className="btn btn-secondary"
          disabled={sortedStudents.length === 0}
          onClick={() => {
            // BOM so Excel reads UTF-8 names correctly when double-clicked.
            const blob = new Blob(['\uFEFF' + studentsCsv(sortedStudents)],
              { type: 'text/csv;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = classGroup
              ? `erd-analytics-students-${classGroup}.csv`
              : 'erd-analytics-students.csv';
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          Export CSV
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
                    {COLUMNS.map((c) => (
                      <th
                        key={c.key}
                        onClick={() => toggleSort(c.key)}
                        aria-sort={
                          sort.key === c.key
                            ? (sort.dir === 'asc' ? 'ascending' : 'descending')
                            : undefined
                        }
                        style={{
                          textAlign: c.numeric ? 'right' : 'left',
                          cursor: 'pointer',
                          userSelect: 'none',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {c.label}
                        <span aria-hidden="true" style={{ marginLeft: 4, fontSize: 10, opacity: sort.key === c.key ? 1 : 0.35 }}>
                          {sort.key === c.key ? (sort.dir === 'asc' ? '▲' : '▼') : '▲▼'}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedStudents.map((s) => (
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
