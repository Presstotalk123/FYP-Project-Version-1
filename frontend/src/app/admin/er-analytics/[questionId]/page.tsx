'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import {
  erAnalyticsService,
  fetchSubmissionImage,
} from '@/services/er-analytics.service';
import type {
  AnalyticsContext,
  QuestionAnalytics,
  StudentSubmissions,
  SubmissionDetail,
} from '@/types/er-analytics.types';

const pct = (v: number | null | undefined): string =>
  v === null || v === undefined ? '—' : `${Math.round(v)}%`;

const rate = (v: number): string => `${Math.round(v * 100)}%`;

function RateBar({ fail, partial }: { fail: number; partial: number }) {
  // Plain CSS bar: red = fail share, yellow = partial share, rest = pass.
  return (
    <div style={{ background: 'var(--surface-muted, #eee)', borderRadius: 4, height: 10, width: 160, overflow: 'hidden', display: 'flex' }}>
      <div style={{ width: `${fail * 100}%`, background: 'var(--error, #e5484d)' }} />
      <div style={{ width: `${partial * 100}%`, background: 'var(--warning, #f5a524)' }} />
    </div>
  );
}

export default function ErQuestionAnalyticsPage() {
  const params = useParams<{ questionId: string }>();
  const router = useRouter();
  const questionId = Number(params.questionId);
  const [context, setContext] = useState<AnalyticsContext>('all');
  const [classGroup, setClassGroup] = useState<string>('');
  const [classGroups, setClassGroups] = useState<string[]>([]);
  const [data, setData] = useState<QuestionAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openStudent, setOpenStudent] = useState<number | null>(null);
  const [journey, setJourney] = useState<StudentSubmissions | null>(null);
  const [attempt, setAttempt] = useState<SubmissionDetail | null>(null);
  const [attemptImage, setAttemptImage] = useState<string | null>(null);

  useEffect(() => {
    erAnalyticsService.classGroups().then(setClassGroups).catch(() => setClassGroups([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setData(null);
      setError(null);
      try {
        const d = await erAnalyticsService.questionAnalytics(
          questionId,
          context,
          classGroup || undefined,
        );
        if (!cancelled) setData(d);
      } catch {
        if (!cancelled) setError('Failed to load analytics');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [questionId, context, classGroup]);

  const openJourney = (studentId: number) => {
    setOpenStudent(studentId);
    setJourney(null);
    erAnalyticsService
      .studentSubmissions(questionId, studentId)
      .then(setJourney)
      .catch(() => setJourney(null));
  };

  const openAttempt = (submissionId: number) => {
    setAttempt(null);
    setAttemptImage(null);
    erAnalyticsService.submissionDetail(submissionId).then((d) => {
      setAttempt(d);
      if (d.has_image) fetchSubmissionImage(d.id).then(setAttemptImage).catch(() => null);
    });
  };

  const closeAttempt = () => {
    if (attemptImage) URL.revokeObjectURL(attemptImage);
    setAttempt(null);
    setAttemptImage(null);
  };

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>ERD Analytics{data ? ` — ${data.title}` : ''}</h2>
            <p>How students performed on this question, check by check.</p>
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
            <select
              className="da-select"
              value={context}
              onChange={(e) => setContext(e.target.value as AnalyticsContext)}
              aria-label="Attempt context"
            >
              <option value="all">All attempts</option>
              <option value="practice">Practice only</option>
              <option value="assessment">Assessments only</option>
            </select>
            <button className="btn btn-secondary" onClick={() => router.push('/admin/er-analytics')}>
              Class overview
            </button>
            {/* Two ways out, because ERD drills one level deeper than SQL does:
                up to the cohort view, or straight back to Problems, which is
                where staff came in from. */}
            <button className="btn btn-secondary" onClick={() => router.push('/admin/problems')}>
              Back to problems
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
              <article className="card"><h3>{data.attempt_count}</h3><p>Attempts</p></article>
              <article className="card"><h3>{data.student_count}</h3><p>Students</p></article>
              <article className="card"><h3>{pct(data.avg_percent)}</h3><p>Average score</p></article>
            </div>

            <h3>Rubric checks</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr><th>Check</th><th>Dimension</th><th>Fail / partial</th><th>Fail rate</th><th>Evaluated</th></tr>
                </thead>
                <tbody>
                  {data.checks.map((c) => (
                    <tr key={c.id}>
                      <td>{c.id} — {c.pass_criteria || '(criteria unavailable)'}</td>
                      <td>{c.dimension}</td>
                      <td><RateBar fail={c.fail_rate} partial={c.partial_rate} /></td>
                      <td>{rate(c.fail_rate)}</td>
                      <td>{c.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginTop: 24 }}>Students</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr><th>Student</th><th>Class</th><th>Attempts</th><th>Best</th><th>Latest</th><th>Last attempt</th></tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.user_id} onClick={() => openJourney(s.user_id)} style={{ cursor: 'pointer' }}>
                      <td>{s.email}</td>
                      <td>{s.class_group ?? '—'}</td>
                      <td>{s.attempts}</td>
                      <td>{pct(s.best_percent)}</td>
                      <td>{pct(s.latest_percent)}</td>
                      <td>{s.last_attempt_at ? new Date(s.last_attempt_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {openStudent !== null && journey && (
              <>
                <h3 style={{ marginTop: 24 }}>
                  Journey — {data.students.find((s) => s.user_id === openStudent)?.email}
                  {'  '}({journey.chat.queries_asked} questions asked to Baloo
                  {journey.chat.topics.length > 0 &&
                    `; asked about: ${journey.chat.topics.join(', ')}`})
                </h3>
                <div className="table-wrap">
                  <table className="da-table">
                    <thead>
                      <tr><th>#</th><th>When</th><th>Score</th><th>Hint level</th><th>Stage</th><th></th></tr>
                    </thead>
                    <tbody>
                      {journey.attempts.map((a, i) => (
                        <tr key={a.id}>
                          <td>{i + 1}</td>
                          <td>{a.created_at ? new Date(a.created_at).toLocaleString() : '—'}</td>
                          <td>{pct(a.percent)} {a.label ? `(${a.label})` : ''}</td>
                          <td>{a.hint_level_at_submit ?? '—'}</td>
                          <td>{a.ibl_stage_at_submit ?? '—'}</td>
                          <td>
                            <button className="btn btn-secondary" onClick={() => openAttempt(a.id)}>
                              View attempt
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}

        {attempt && (
          <div
            role="dialog"
            aria-label={`Submission ${attempt.id}`}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 }}
            onClick={closeAttempt}
          >
            <div className="card" style={{ maxWidth: 1000, width: '90%', maxHeight: '85vh', overflow: 'auto' }} onClick={(e) => e.stopPropagation()}>
              <div className="page-head">
                <h3>Attempt — {pct(attempt.score_percent)} ({attempt.score_label ?? 'ungraded'})</h3>
                <button className="btn btn-secondary" onClick={closeAttempt}>Close</button>
              </div>
              <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 420px' }}>
                  {attemptImage ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={attemptImage} alt="Submitted ER diagram" style={{ maxWidth: '100%', border: '1px solid var(--border, #ddd)' }} />
                  ) : attempt.submitted_xml ? (
                    <pre style={{ maxHeight: 400, overflow: 'auto' }}>{attempt.submitted_xml}</pre>
                  ) : (
                    <p>No diagram stored for this attempt.</p>
                  )}
                  {attempt.submission_description && <p><em>{attempt.submission_description}</em></p>}
                </div>
                <div style={{ flex: '1 1 320px' }}>
                  <table className="da-table">
                    <thead><tr><th>Check</th><th>Status</th><th>Reason</th></tr></thead>
                    <tbody>
                      {attempt.checks.map((c) => (
                        <tr key={c.id}>
                          <td>{c.id}</td>
                          <td><span className={`badge ${c.status === 'pass' ? 'badge-success' : c.status === 'partial' ? 'badge-warn' : 'badge-error'}`}>{c.status}</span></td>
                          <td>{c.brief_reason ?? ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
