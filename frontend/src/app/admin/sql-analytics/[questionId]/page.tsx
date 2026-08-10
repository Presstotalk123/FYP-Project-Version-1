'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { sqlAnalyticsService } from '@/services/sql-analytics.service';
import { erAnalyticsService } from '@/services/er-analytics.service';
import type {
  SqlQuestionAnalytics,
  SqlStudentDetail,
} from '@/types/sql-analytics.types';

const num = (v: number | null | undefined): string =>
  v === null || v === undefined ? '—' : String(v);

const when = (v: string | null): string =>
  v ? new Date(v).toLocaleString() : '—';

export default function SqlQuestionAnalyticsPage() {
  const params = useParams<{ questionId: string }>();
  const router = useRouter();
  const questionId = Number(params.questionId);
  const [classGroup, setClassGroup] = useState<string>('');
  const [classGroups, setClassGroups] = useState<string[]>([]);
  const [data, setData] = useState<SqlQuestionAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openStudent, setOpenStudent] = useState<number | null>(null);
  const [detail, setDetail] = useState<SqlStudentDetail | null>(null);

  useEffect(() => {
    erAnalyticsService.classGroups().then(setClassGroups).catch(() => setClassGroups([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setData(null);
      setError(null);
      try {
        const d = await sqlAnalyticsService.questionAnalytics(questionId, classGroup || undefined);
        if (!cancelled) setData(d);
      } catch {
        if (!cancelled) setError('Failed to load analytics');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [questionId, classGroup]);

  const openDetail = (studentId: number) => {
    setOpenStudent(studentId);
    setDetail(null);
    sqlAnalyticsService
      .studentDetail(questionId, studentId)
      .then(setDetail)
      .catch(() => setDetail(null));
  };

  const closeDetail = () => {
    setOpenStudent(null);
    setDetail(null);
  };

  const openEmail = data?.students.find((s) => s.user_id === openStudent)?.email;

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>Question Analytics{data ? ` — ${data.title}` : ''}</h2>
            <p>How students worked through this SQL question.</p>
          </div>
          <div className="button-row">
            <select
              className="da-select"
              value={classGroup}
              onChange={(e) => setClassGroup(e.target.value)}
              aria-label="Class group"
            >
              <option value="">All classes</option>
              {classGroups.map((g) => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
            <button className="btn btn-secondary" onClick={() => router.push('/admin/questions')}>
              Back to questions
            </button>
          </div>
        </div>

        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {data && (
          <>
            <div className="grid-3" style={{ marginBottom: 20 }}>
              <article className="card"><h3>{data.student_count}</h3><p>Students attempted</p></article>
              <article className="card"><h3>{num(data.avg_queries_to_correct)}</h3><p>Mean queries to correct</p></article>
              <article className="card"><h3>{data.chatbot_student_count}</h3><p>Used AI chatbot</p></article>
            </div>

            <h3>Students</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr>
                    <th>Student</th><th>Class</th><th>Attempts</th><th>Queries to correct</th>
                    <th>Solved</th><th>Used chatbot</th><th>Last attempt</th>
                  </tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.user_id} onClick={() => openDetail(s.user_id)} style={{ cursor: 'pointer' }}>
                      <td>{s.email}</td>
                      <td>{s.class_group ?? '—'}</td>
                      <td>{s.attempts_count}</td>
                      <td>{num(s.queries_to_correct)}</td>
                      <td>{s.completed ? 'Yes' : 'No'}</td>
                      <td>{s.used_chatbot ? 'Yes' : 'No'}</td>
                      <td>{when(s.last_attempted_at)}</td>
                    </tr>
                  ))}
                  {data.students.length === 0 && (
                    <tr><td colSpan={7}>No students have attempted this question yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {openStudent !== null && (
          <div
            role="dialog"
            aria-label="Student detail"
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 }}
            onClick={closeDetail}
          >
            <div className="card" style={{ maxWidth: 1000, width: '92%', maxHeight: '88vh', overflow: 'auto' }} onClick={(e) => e.stopPropagation()}>
              <div className="page-head">
                <h3>{openEmail ?? 'Student'}</h3>
                <button className="btn btn-secondary" onClick={closeDetail}>Close</button>
              </div>

              {!detail && <p>Loading…</p>}
              {detail && (
                <>
                  <h4>Query history</h4>
                  <div className="table-wrap">
                    <table className="da-table">
                      <thead><tr><th>#</th><th>When</th><th>Correct</th><th>Query</th><th>Error</th></tr></thead>
                      <tbody>
                        {detail.query_history.map((q, i) => (
                          <tr key={q.id}>
                            <td>{i + 1}</td>
                            <td>{when(q.submitted_at)}</td>
                            <td>{q.is_correct ? 'Yes' : 'No'}</td>
                            <td><pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{q.query}</pre></td>
                            <td>{q.error_message ?? ''}</td>
                          </tr>
                        ))}
                        {detail.query_history.length === 0 && <tr><td colSpan={5}>No queries recorded.</td></tr>}
                      </tbody>
                    </table>
                  </div>

                  <h4 style={{ marginTop: 20 }}>AI query-review history</h4>
                  <div className="table-wrap">
                    <table className="da-table">
                      <thead><tr><th>When</th><th>Query</th><th>Problem</th><th>Explanation</th><th>Hint</th></tr></thead>
                      <tbody>
                        {detail.review_history.map((r) => (
                          <tr key={r.id}>
                            <td>{when(r.created_at)}</td>
                            <td><pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{r.student_query}</pre></td>
                            <td>{r.problem_token ?? ''}</td>
                            <td>{r.explanation ?? ''}</td>
                            <td>{r.hint ?? ''}</td>
                          </tr>
                        ))}
                        {detail.review_history.length === 0 && <tr><td colSpan={5}>No AI query reviews recorded.</td></tr>}
                      </tbody>
                    </table>
                  </div>

                  <h4 style={{ marginTop: 20 }}>Chatbot transcript</h4>
                  {detail.chatbot.length === 0 ? (
                    <p>No chatbot conversation.</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {detail.chatbot.map((m, i) => (
                        <div key={i} className="card" style={{ padding: 10 }}>
                          <strong>{m.role === 'assistant' ? 'Tutor' : 'Student'}</strong>
                          <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
                          <small style={{ opacity: 0.6 }}>{when(m.created_at)}</small>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
