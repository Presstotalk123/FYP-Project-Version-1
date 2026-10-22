'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { ClassGroupSelect, TopErrors, VERDICT_INFO, VerdictBar, when } from '@/components/ra/RaAnalyticsParts';
import { RaOff } from '@/components/ra/RaOff';
import { useRaStatus } from '@/hooks/use-ra-status';
import { raQueryKeys, raService } from '@/services/ra.service';
import { UserRole } from '@/types/user.types';

/** One RA question for staff: each part's results and mistakes, each student's parts, and their attempts. */
export default function RaQuestionAnalyticsPage() {
  const { enabled, loading } = useRaStatus();
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        {loading ? null : !enabled ? <RaOff /> : <QuestionAnalytics />}
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function QuestionAnalytics() {
  const params = useParams();
  const questionId = parseInt((params?.id as string) || '0');
  // ?student=<id> (from an assessment's student list) opens that student's attempts straight away.
  const focus = Number(useSearchParams().get('student')) || null;
  const [classGroup, setClassGroup] = useState('');
  const [openStudent, setOpenStudent] = useState<number | null>(focus);
  const query = useQuery({
    queryKey: raQueryKeys.questionAnalytics(questionId, classGroup),
    queryFn: () => raService.questionAnalytics(questionId, classGroup),
    placeholderData: (prev) => prev,
  });
  const data = query.data;
  const multi = (data?.parts.length ?? 0) > 1;

  return (
    <>
      <div className="button-row" style={{ marginBottom: 12 }}>
        <Link href="/ra/analytics" className="btn btn-ghost" style={{ minHeight: 30, fontSize: 13 }}>← Class analytics</Link>
        <Link href={`/ra/questions/${questionId}`} className="btn btn-ghost" style={{ minHeight: 30, fontSize: 13, marginLeft: 'auto' }}>
          Open the question
        </Link>
      </div>
      <div className="page-head">
        <div>
          <h2>Question Analytics{data ? ` — ${data.title}` : ''}</h2>
          <p>
            How students worked through this RA question{multi ? ', part by part' : ''}.
            {data?.is_assessment_copy && ' This is an assessment’s copy of the question: these are that assessment’s attempts.'}
          </p>
        </div>
        <ClassGroupSelect value={classGroup} onChange={setClassGroup} />
      </div>

      {query.isLoading ? (
        <div className="loading-center"><div className="spinner" /><span>Loading…</span></div>
      ) : query.error || !data ? (
        <div className="da-alert alert-error" role="alert"><strong>Error</strong><span>Failed to load analytics.</span></div>
      ) : (
        <div style={{ display: 'grid', gap: 22, opacity: query.isFetching ? 0.6 : 1 }}>
          <div className="grid-3">
            <article className="card"><h3>{data.student_count}</h3><p>Students attempted</p></article>
            <article className="card"><h3>{data.solved_count}</h3><p>Solved {multi ? 'every part' : 'it'}</p></article>
            <article className="card">
              <h3>{data.parts.reduce((n, p) => n + p.attempts, 0)}</h3><p>Submissions</p>
            </article>
          </div>

          <section style={{ display: 'grid', gap: 12 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>{multi ? 'Parts' : 'Results'}</h3>
            {data.parts.map((p) => (
              <article key={p.part_id} className="card" style={{ padding: 16, display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                  {multi && <strong>Part {p.label}</strong>}
                  {multi && <span className="badge neutral">{p.marks} mark{p.marks === 1 ? '' : 's'}</span>}
                  <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                    {p.students_solved} of {p.students} student{p.students === 1 ? '' : 's'} solved it · {p.attempts} submission
                    {p.attempts === 1 ? '' : 's'}
                    {p.avg_submits_to_correct != null && ` · ${p.avg_submits_to_correct} submissions to correct on average`}
                  </span>
                </div>
                <VerdictBar verdicts={p.verdicts} />
                {p.top_errors.length > 0 && <TopErrors errors={p.top_errors} />}
              </article>
            ))}
          </section>

          <section style={{ display: 'grid', gap: 8 }}>
            <h3 style={{ margin: 0, fontSize: 16 }}>Students</h3>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
              Click a student to see every answer they submitted and what the grader said.
            </p>
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr>
                    <th>Student</th><th>Class</th>
                    {data.parts.map((p) => <th key={p.part_id}>{multi ? `Part ${p.label}` : 'Result'}</th>)}
                    <th style={{ textAlign: 'right' }}>Marks</th><th>Last attempt</th>
                  </tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.user_id} onClick={() => setOpenStudent(s.user_id)} style={{ cursor: 'pointer' }}>
                      <td>
                        <div style={{ fontWeight: 600 }}><span className="pii">{s.name || s.email}</span></div>
                        {s.name && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}><span className="pii">{s.email}</span></div>}
                      </td>
                      <td>{s.class_group || '—'}</td>
                      {s.parts.map((c) => (
                        <td key={c.part_id} style={{ fontSize: 13 }}>
                          {c.attempts === 0 ? <span style={{ color: 'var(--text-muted)' }}>—</span>
                            : c.solved ? <span style={{ color: 'var(--success)' }}>✓ in {c.submits_to_correct}</span>
                              : (
                                <span title={c.last_verdict ? VERDICT_INFO[c.last_verdict].hint : undefined}>
                                  ✗ {c.attempts} · {c.last_verdict ? VERDICT_INFO[c.last_verdict].label : ''}
                                </span>
                              )}
                        </td>
                      ))}
                      <td style={{ textAlign: 'right' }}>{s.marks_earned} / {s.marks_total}</td>
                      <td>{when(s.last_attempt_at)}</td>
                    </tr>
                  ))}
                  {data.students.length === 0 && (
                    <tr><td colSpan={data.parts.length + 4}>No students have attempted this question yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {openStudent !== null && (
        <StudentAttempts questionId={questionId} studentId={openStudent} onClose={() => setOpenStudent(null)} />
      )}
    </>
  );
}

function StudentAttempts({ questionId, studentId, onClose }: { questionId: number; studentId: number; onClose: () => void }) {
  const query = useQuery({
    queryKey: raQueryKeys.studentAttempts(questionId, studentId),
    queryFn: () => raService.studentAttempts(questionId, studentId),
  });
  const data = query.data;
  return (
    <div role="dialog" aria-label="Student attempts" onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center',
        justifyContent: 'center', zIndex: 200 }}>
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 1000, width: '92%', maxHeight: '88vh', overflow: 'auto', padding: 20 }}>
        <div className="page-head">
          <h3 style={{ margin: 0 }}>{data ? <span className="pii">{data.name || data.email}</span> : 'Student'}</h3>
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
        {query.isLoading && <p>Loading…</p>}
        {query.error && <div className="alert-error">Could not load the attempts.</div>}
        {data && data.attempts.length === 0 && <p>No attempts recorded.</p>}
        {data && data.attempts.length > 0 && (
          <div className="table-wrap">
            <table className="da-table">
              <thead><tr><th>#</th><th>When</th><th>Part</th><th>Answer</th><th>Verdict</th></tr></thead>
              <tbody>
                {data.attempts.map((a, i) => (
                  <tr key={a.id}>
                    <td>{i + 1}</td>
                    <td style={{ whiteSpace: 'nowrap', fontSize: 13 }}>{when(a.created_at)}</td>
                    <td>{a.part_label || '—'}</td>
                    <td><pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'var(--font-geist-mono)', fontSize: 12 }}>{a.answer}</pre></td>
                    <td style={{ fontSize: 13 }}>
                      <strong style={{ color: a.correct ? 'var(--success)' : 'var(--error)' }}>
                        {VERDICT_INFO[a.verdict]?.label ?? a.verdict}
                      </strong>
                      {a.overridden && <span className="badge neutral" style={{ marginLeft: 6 }}>overridden: {a.correct ? 'correct' : 'wrong'}</span>}
                      {a.error ? (
                        <div style={{ color: 'var(--text-muted)' }}>
                          <code>{a.error.code}</code> {a.error.line ? `line ${a.error.line}: ` : ''}{a.error.message}
                        </div>
                      ) : a.message && !a.correct && <div style={{ color: 'var(--text-muted)' }}>{a.message}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
