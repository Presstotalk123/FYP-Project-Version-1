'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { raQueryKeys, raService } from '@/services/ra.service';
import { ClassGroupSelect, downloadCsv, percent, TopErrors, VerdictBar } from './RaAnalyticsParts';

const METRIC_LABEL: React.CSSProperties = {
  fontSize: 13, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em',
};
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '—');

/**
 * RA analytics for the class, over every practice question: totals, how attempts split by
 * verdict, the commonest errors, each question (click for its parts and students) and each
 * student. Students only; used on /ra/analytics and as the staff dashboard's RA tab.
 */
export function RaClassAnalytics() {
  const router = useRouter();
  const [classGroup, setClassGroup] = useState('');
  const query = useQuery({
    queryKey: raQueryKeys.classAnalytics(classGroup),
    queryFn: () => raService.classAnalytics(classGroup),
    placeholderData: (prev) => prev,
  });
  const data = query.data;
  const students = [...(data?.students ?? [])].sort((a, b) => b.submissions - a.submissions);

  const exportCsv = () => downloadCsv(
    classGroup ? `ra-analytics-students-${classGroup}.csv` : 'ra-analytics-students.csv',
    ['Name', 'Email', 'Class group', 'Submissions', 'Questions tried', 'Parts tried', 'Parts solved',
      'Completion %', 'First activity', 'Last activity'],
    students.map((s) => [s.name ?? '', s.email, s.class_group ?? '', s.submissions, s.questions_tried,
      s.parts_tried, s.parts_solved, s.completion_percent, s.first_activity_at, s.last_activity_at]),
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Relational Algebra Analytics</h2>
          <p>How students work through the RA practice questions, and where they go wrong.</p>
        </div>
        <div className="button-row">
          <ClassGroupSelect value={classGroup} onChange={setClassGroup} />
          <button className="btn btn-secondary" disabled={students.length === 0} onClick={exportCsv}>Export CSV</button>
        </div>
      </div>

      {query.isLoading ? (
        <div className="loading-center"><div className="spinner" /><span>Loading RA analytics…</span></div>
      ) : query.error ? (
        <div className="da-alert alert-error" role="alert"><strong>Error</strong><span>Failed to load RA analytics.</span></div>
      ) : data && (
        <div style={{ display: 'grid', gap: 22, opacity: query.isFetching ? 0.6 : 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 16 }}>
            <Metric label="Submissions" value={data.totals.submissions} note="graded RA answers" color="var(--brand-lilac)" />
            <Metric label="Students engaged" value={data.totals.students_engaged}
              note={`of ${data.totals.registered_students} registered`} color="var(--success)" />
            <Metric label="Avg completion"
              value={data.totals.avg_completion_percent == null ? '—' : `${data.totals.avg_completion_percent}%`}
              note="parts solved / parts tried" color="var(--info)" />
            <Metric label="Questions" value={data.totals.questions} note="in the practice bank" color="var(--warning)" />
          </div>

          <section className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Where students go wrong</h3>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
              Every submitted answer, by the grader&apos;s verdict. Hover a colour for what it means.
            </p>
            <VerdictBar verdicts={data.verdicts} />
            <h4 style={{ margin: '6px 0 0', fontSize: 14 }}>Commonest errors in answers that could not be run</h4>
            <TopErrors errors={data.top_errors} />
          </section>

          <section style={{ display: 'grid', gap: 8 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Questions</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr>
                    <th>Question</th><th style={{ textAlign: 'right' }}>Parts</th><th style={{ textAlign: 'right' }}>Students</th>
                    <th style={{ textAlign: 'right' }}>Solved all parts</th><th style={{ textAlign: 'right' }}>Attempts</th>
                    <th>Verdicts</th>
                  </tr>
                </thead>
                <tbody>
                  {data.questions.map((q) => (
                    <tr key={q.question_id} onClick={() => router.push(`/ra/analytics/${q.question_id}`)} style={{ cursor: 'pointer' }}>
                      <td>
                        {q.title}
                        {!q.is_published && <span className="badge badge-warn" style={{ marginLeft: 6 }}>Draft</span>}
                      </td>
                      <td style={{ textAlign: 'right' }}>{q.parts}</td>
                      <td style={{ textAlign: 'right' }}>{q.students}</td>
                      <td style={{ textAlign: 'right' }}>{q.students ? `${q.students_solved} (${percent(q.completion_rate)})` : '—'}</td>
                      <td style={{ textAlign: 'right' }}>{q.attempts}</td>
                      <td><VerdictBar verdicts={q.verdicts} compact /></td>
                    </tr>
                  ))}
                  {data.questions.length === 0 && <tr><td colSpan={6}>No RA questions yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <section style={{ display: 'grid', gap: 8 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Students</h3>
            {students.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', margin: 0 }}>No RA activity recorded yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="da-table">
                  <thead>
                    <tr>
                      <th>Student</th><th>Class</th><th style={{ textAlign: 'right' }}>Submissions</th>
                      <th style={{ textAlign: 'right' }}>Questions tried</th><th style={{ textAlign: 'right' }}>Parts solved</th>
                      <th style={{ textAlign: 'right' }}>Completion</th><th>First activity</th><th>Last activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {students.map((s) => (
                      <tr key={s.user_id}>
                        <td>
                          <div style={{ fontWeight: 600 }}><span className="pii">{s.name || s.email}</span></div>
                          {s.name && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}><span className="pii">{s.email}</span></div>}
                        </td>
                        <td>{s.class_group || '—'}</td>
                        <td style={{ textAlign: 'right' }}>{s.submissions}</td>
                        <td style={{ textAlign: 'right' }}>{s.questions_tried}</td>
                        <td style={{ textAlign: 'right' }}>{s.parts_solved} of {s.parts_tried}</td>
                        <td style={{ textAlign: 'right' }}>{s.completion_percent == null ? '—' : `${s.completion_percent}%`}</td>
                        <td>{day(s.first_activity_at)}</td>
                        <td>{day(s.last_activity_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function Metric({ label, value, note, color }: { label: string; value: string | number; note: string; color: string }) {
  return (
    <article className="card metric" style={{ borderLeft: `3px solid ${color}` }}>
      <div>
        <span style={METRIC_LABEL}>{label}</span>
        <strong>{value}</strong>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{note}</span>
      </div>
    </article>
  );
}
