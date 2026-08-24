'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { ErRegradeControl } from '@/components/admin/ErRegradeControl';
import {
  DRAWIO_RENDERER_URL,
  OFFSCREEN_FRAME_STYLE,
  useErXmlToPng,
} from '@/components/admin/useErXmlToPng';
import { UserRole } from '@/types/user.types';
import {
  erAnalyticsService,
  fetchSubmissionImage,
  overrideSubmissionScore,
  revertSubmissionScore,
} from '@/services/er-analytics.service';
import { getApiErrorMessage } from '@/utils/api-error';
import type {
  AnalyticsContext,
  QuestionAnalytics,
  StudentSubmissions,
  SubmissionCheck,
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
  // Draws a stored XML source into the same white-background PNG a student's submit
  // produces, so an attempt with no stored picture still reaches the normal <img>.
  const { frameRef: rendererFrameRef, render } = useErXmlToPng();

  // Score-override editing. `editing` gates it so a stray click can never change a
  // mark. `awards` is seeded from what the grader gave every scoring check, so it
  // always holds the complete picture — no diffing against the original, and the
  // save sends the lot.
  const [editing, setEditing] = useState(false);
  /** check id -> points, as typed. Strings, so clearing a box does not snap to 0
   *  under the cursor mid-edit. */
  const [awards, setAwards] = useState<Record<string, string>>({});
  /** The submitted diagram, opened over the modal to check detail while marking. */
  const [imageZoomed, setImageZoomed] = useState(false);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [overrideError, setOverrideError] = useState<string | null>(null);
  // Bumped after an override so the aggregates behind this page refetch: a
  // corrected score changes the average, the histogram and the check rates.
  const [reloadKey, setReloadKey] = useState(0);

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
  }, [questionId, context, classGroup, reloadKey]);

  // ?student=<id> opens that student's attempts straight away, so a link from the
  // assessment gradebook lands on the person being looked at rather than on the
  // class table with them still to be found.
  const searchParams = useSearchParams();
  const focusStudent = Number(searchParams.get('student')) || null;
  const autoOpened = useRef(false);
  // ?regrade=1 opens the regrade dialog on arrival — the rubric editor routes
  // here after a save so "save, then choose whether to regrade" is one flow.
  const autoRegrade = searchParams.get('regrade') === '1';

  useEffect(() => {
    if (!focusStudent || autoOpened.current || !data) return;
    autoOpened.current = true;
    openJourney(focusStudent);
    // openJourney is redefined every render; the ref is what makes this run once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusStudent, data]);

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
      if (d.has_image) {
        fetchSubmissionImage(d.id).then(setAttemptImage).catch(() => null);
        return;
      }
      // Attempts added before submissions carried a picture, and the rare one whose
      // render failed, still hold their draw.io XML. Draw it here so every attempt
      // reaches the same <img> and the same zoom, instead of a second kind of viewer.
      if (d.submitted_xml) {
        void render(d.submitted_xml).then((file) => {
          if (file) setAttemptImage(URL.createObjectURL(file));
        });
      }
    });
  };

  const closeAttempt = () => {
    if (attemptImage) URL.revokeObjectURL(attemptImage);
    setAttempt(null);
    setAttemptImage(null);
    setImageZoomed(false);
    stopEditing();
  };

  /** Straight to the attempt that carries the student's mark, skipping the journey.
   *  Marking is the common errand here; the journey is for studying a progression. */
  const markLatest = async (studentId: number) => {
    const journeyForStudent = await erAnalyticsService.studentSubmissions(questionId, studentId);
    const latest = journeyForStudent.attempts[journeyForStudent.attempts.length - 1];
    if (!latest) return;
    setOpenStudent(studentId);
    setJourney(journeyForStudent);
    openAttempt(latest.id);
  };

  const stopEditing = () => {
    setEditing(false);
    setAwards({});
    setReason('');
    setOverrideError(null);
  };

  /** Whether a check counts toward the total at all. */
  const isScoring = (c: SubmissionCheck) =>
    (c.requirement_level === 'must' || c.requirement_level === 'should') &&
    c.status !== 'not_applicable';

  /** Seed every scoring check with what it currently carries, so the map is complete
   *  from the outset and editing is just typing over a value. */
  const startEditing = (checks: SubmissionCheck[]) => {
    const seed: Record<string, string> = {};
    for (const c of checks) {
      if (isScoring(c)) seed[c.id] = String(c.earned_points ?? 0);
    }
    setAwards(seed);
    setEditing(true);
  };

  /** Running total, so the consequence of an edit is visible before saving. The
   *  server re-totals independently and its answer is what gets stored. */
  const preview = (checks: SubmissionCheck[]) => {
    let earned = 0;
    let total = 0;
    let valid = true;
    for (const c of checks) {
      if (!isScoring(c)) continue;
      const points = c.points ?? 0;
      const n = Number(awards[c.id]);
      total += points;
      if (!Number.isFinite(n) || n < 0 || n > points) valid = false;
      else earned += n;
    }
    return { earned, total, percent: total > 0 ? Math.round((100 * earned) / total) : 0, valid };
  };

  /** Refresh the aggregates behind this page — an override changes them. */
  const refreshAnalytics = () => {
    setReloadKey((k) => k + 1);
    if (openStudent !== null) openJourney(openStudent);
  };

  const saveOverride = async () => {
    if (!attempt) return;
    setSaving(true);
    setOverrideError(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(awards).map(([id, v]) => [id, Number(v)]),
      );
      await overrideSubmissionScore(attempt.id, payload, reason);
      const fresh = await erAnalyticsService.submissionDetail(attempt.id);
      setAttempt(fresh);
      stopEditing();
      refreshAnalytics();
    } catch (err) {
      setOverrideError(getApiErrorMessage(err, 'Failed to save the override'));
    } finally {
      setSaving(false);
    }
  };

  const revertOverride = async () => {
    if (!attempt) return;
    setSaving(true);
    setOverrideError(null);
    try {
      await revertSubmissionScore(attempt.id);
      const fresh = await erAnalyticsService.submissionDetail(attempt.id);
      setAttempt(fresh);
      stopEditing();
      refreshAnalytics();
    } catch (err) {
      setOverrideError(getApiErrorMessage(err, 'Failed to revert the override'));
    } finally {
      setSaving(false);
    }
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

        <ErRegradeControl
          questionId={questionId}
          classGroups={classGroups}
          autoOpen={autoRegrade}
          onFinished={() => setReloadKey((k) => k + 1)}
        />

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

            {/* What students got stuck on here specifically — the class overview
                answers the same question for the whole cohort, which does not tell
                you whether THIS problem statement is the confusing one. */}
            <h3 style={{ marginTop: 24 }}>What students asked Baloo</h3>
            {/* Defaulted, not assumed: analytics payloads are cached whole, so an
                entry computed before this field existed is still servable — and
                reading .length off it would take the page down. */}
            {(data.query_topics ?? []).length === 0 ? (
              <p style={{ color: 'var(--text-muted)' }}>
                No tutor questions asked on this question yet.
              </p>
            ) : (
              <div className="table-wrap">
                <table className="da-table">
                  <thead><tr><th>Topic</th><th>Questions</th><th>Recent examples</th></tr></thead>
                  <tbody>
                    {(data.query_topics ?? []).map((t) => (
                      <tr key={t.topic}>
                        <td>{t.topic}</td>
                        <td>{t.count}</td>
                        <td>
                          <details>
                            <summary style={{ cursor: 'pointer' }}>{t.examples[0] ?? ''}</summary>
                            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                              {t.examples.slice(1).map((q) => (
                                <li key={q} style={{ fontSize: 13 }}>{q}</li>
                              ))}
                            </ul>
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <h3 style={{ marginTop: 24 }}>Students</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr><th>Student</th><th>Name</th><th>Class</th><th>Attempts</th><th>Best</th><th>Latest</th><th>Last attempt</th><th></th></tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.user_id} onClick={() => openJourney(s.user_id)} style={{ cursor: 'pointer' }}>
                      <td>{s.email}</td>
                      <td>{s.name || '—'}</td>
                      <td>{s.class_group ?? '—'}</td>
                      <td>{s.attempts}</td>
                      <td>{pct(s.best_percent)}</td>
                      <td>{pct(s.latest_percent)}</td>
                      <td>{s.last_attempt_at ? new Date(s.last_attempt_at).toLocaleString() : '—'}</td>
                      <td>
                        <button
                          className="btn btn-secondary"
                          aria-label={`Mark ${s.email}`}
                          onClick={(e) => {
                            // The row opens the journey; this skips it.
                            e.stopPropagation();
                            markLatest(s.user_id);
                          }}
                        >
                          Mark
                        </button>
                      </td>
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
                          <td>
                            {pct(a.percent)} {a.label ? `(${a.label})` : ''}
                            {a.regraded_at && (
                              <span
                                className="badge badge-info"
                                style={{ marginLeft: 8 }}
                                title={`Regraded ${new Date(a.regraded_at).toLocaleString()}`}
                              >
                                Regraded
                              </span>
                            )}
                          </td>
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
            {/* A column that does not scroll as a whole: the header stays, the panes
                below scroll independently, and the running total sits at the bottom.
                Scrolling the checks used to carry the diagram off screen, which is
                the one thing you need in view while marking against it. */}
            <div
              className="card"
              style={{
                maxWidth: 1100, width: '92%', height: '85vh',
                display: 'flex', flexDirection: 'column', overflow: 'hidden',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="page-head" style={{ flexShrink: 0 }}>
                <h3>Attempt — {pct(attempt.score_percent)} ({attempt.score_label ?? 'ungraded'})</h3>
                <div className="button-row">
                  {!editing && (
                    <button className="btn btn-secondary" onClick={() => startEditing(attempt.checks)}>
                      Adjust score
                    </button>
                  )}
                  <button className="btn btn-secondary" onClick={closeAttempt}>Close</button>
                </div>
              </div>

              {attempt.override && (
                <div className="da-alert alert-info" style={{ fontSize: 12 }}>
                  <span>
                    Overridden from {pct(attempt.override.original_score.percent)} by{' '}
                    {attempt.override.by_email ?? 'staff'} on{' '}
                    {new Date(attempt.override.at).toLocaleString()} — “{attempt.override.reason}”
                  </span>
                </div>
              )}

              {attempt.regraded_at && (
                <div className="da-alert alert-info" style={{ fontSize: 12 }}>
                  <span>
                    Regraded against the current rubric on{' '}
                    {new Date(attempt.regraded_at).toLocaleString()}.
                  </span>
                </div>
              )}

              {editing && !attempt.is_latest_attempt && (
                <div className="da-alert alert-warn" style={{ fontSize: 12 }}>
                  <span>
                    This is not the student’s most recent attempt. Adjusting it updates
                    analytics but not their assessment mark.
                  </span>
                </div>
              )}

              {overrideError && (
                <div className="da-alert alert-error" role="alert" style={{ fontSize: 12 }}>
                  <span>{overrideError}</span>
                </div>
              )}
              {/* min-height: 0 is what lets the children scroll instead of stretching
                  this row to fit their content. */}
              <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
                <div style={{ flex: '1 1 45%', minWidth: 0, overflow: 'auto' }}>
                  {attemptImage ? (
                    <button
                      type="button"
                      onClick={() => setImageZoomed(true)}
                      aria-label="Enlarge submitted diagram"
                      title="Click to enlarge"
                      style={{ padding: 0, border: 'none', background: 'none', cursor: 'zoom-in', lineHeight: 0, width: '100%' }}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={attemptImage} alt="Submitted ER diagram" style={{ maxWidth: '100%', border: '1px solid var(--border, #ddd)' }} />
                    </button>
                  ) : attempt.submitted_xml ? (
                    // The picture is still being drawn from the XML (see openAttempt),
                    // or draw.io did not answer. The source stays available either way.
                    <>
                      <p>Drawing the diagram…</p>
                      <details>
                        <summary style={{ cursor: 'pointer' }}>Show the diagram source</summary>
                        <pre style={{ margin: '8px 0 0', maxHeight: 240, overflow: 'auto' }}>
                          {attempt.submitted_xml}
                        </pre>
                      </details>
                    </>
                  ) : (
                    <p>No diagram stored for this attempt.</p>
                  )}
                  {attempt.submission_description && <p><em>{attempt.submission_description}</em></p>}
                </div>
                <div style={{ flex: '1 1 55%', minWidth: 0, overflow: 'auto' }}>
                  <table className="da-table">
                    <thead>
                      <tr>
                        <th>Check</th>
                        <th>What it tests</th>
                        <th>Status</th>
                        <th style={{ textAlign: 'right' }}>{editing ? 'Points' : 'Awarded'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attempt.checks.map((c) => {
                        const scoring = isScoring(c);
                        const points = c.points ?? 0;
                        const typed = Number(awards[c.id]);
                        const bad = editing && scoring &&
                          (!Number.isFinite(typed) || typed < 0 || typed > points);
                        const changed = editing && scoring && !bad &&
                          typed !== (c.earned_points ?? 0);
                        const status = c.status;
                        return (
                          <tr key={c.id}>
                            <td style={{ whiteSpace: 'nowrap' }}>
                              {c.id}
                              {c.requirement_level && (
                                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                  {c.requirement_level}
                                </div>
                              )}
                            </td>
                            <td style={{ fontSize: 13 }}>
                              {c.pass_criteria || <em style={{ color: 'var(--text-muted)' }}>criteria unavailable</em>}
                              {/* The grader's own words: what staff are judging. */}
                              {c.brief_reason && (
                                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                                  Grader: {c.brief_reason}
                                </div>
                              )}
                            </td>
                            <td>
                              <span className={`badge ${status === 'pass' ? 'badge-success' : status === 'partial' ? 'badge-warn' : status === 'not_applicable' ? 'neutral' : 'badge-error'}`}>
                                {status === 'not_applicable' ? 'not evaluated' : status}
                              </span>
                            </td>
                            <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                              {!scoring ? (
                                <span style={{ color: 'var(--text-muted)' }}>—</span>
                              ) : editing ? (
                                <>
                                  <input
                                    className="da-input"
                                    type="number"
                                    min={0}
                                    max={points}
                                    step="any"
                                    style={{ width: 76, textAlign: 'right' }}
                                    aria-label={`Points for ${c.id}`}
                                    value={awards[c.id] ?? ''}
                                    onChange={(e) =>
                                      setAwards((a) => ({ ...a, [c.id]: e.target.value }))
                                    }
                                  />
                                  {' / '}{points}
                                  {bad && (
                                    <div style={{ fontSize: 11, color: 'var(--error)' }}>
                                      0–{points}
                                    </div>
                                  )}
                                  {changed && (
                                    <div>
                                      <span className="badge badge-info">changed</span>
                                    </div>
                                  )}
                                </>
                              ) : (
                                <>{c.earned_points ?? 0} / {points}</>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Outside the scrolling panes: the running total and the save controls
                  stay in view however far down the checks you are. */}
              {editing && (() => {
                const p = preview(attempt.checks);
                return (
                  <div
                    style={{
                      flexShrink: 0, display: 'grid', gap: 8, paddingTop: 12, marginTop: 12,
                      borderTop: '1px solid var(--border, #ddd)',
                    }}
                  >
                    <div style={{ fontWeight: 700 }}>
                      New score: {p.earned} / {p.total} = {p.percent}%{' '}
                      <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>
                        (was {pct(attempt.score_percent)})
                      </span>
                    </div>
                    <div className="button-row" style={{ alignItems: 'center' }}>
                      <input
                        className="da-input"
                        style={{ flex: 1, minWidth: 200 }}
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="Reason (optional)"
                        aria-label="Reason for the score change"
                      />
                      <button className="btn btn-secondary" onClick={stopEditing} disabled={saving}>
                        Cancel
                      </button>
                      {attempt.override && (
                        <button className="btn btn-secondary" onClick={revertOverride} disabled={saving}>
                          Revert to AI score
                        </button>
                      )}
                      <button
                        className="btn btn-brand"
                        onClick={saveOverride}
                        /* Only a value the server would reject blocks the save. */
                        disabled={saving || !p.valid}
                      >
                        {saving ? 'Saving…' : 'Save'}
                      </button>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        )}

        {/* Over the marking modal, not instead of it — closing returns to the checks
            with every point already typed still in place. */}
        {imageZoomed && attemptImage && (
          <div
            role="dialog"
            aria-label="Submitted diagram, full size"
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 300, overflow: 'auto', padding: 16 }}
            onClick={() => setImageZoomed(false)}
          >
            <div className="button-row" style={{ justifyContent: 'flex-end', marginBottom: 8 }}>
              {/* Not just "Close": the marking modal underneath has one too, and two
                  identically named buttons are ambiguous to anyone not seeing the
                  overlay sitting on top. */}
              <button className="btn btn-secondary" onClick={() => setImageZoomed(false)}>
                Close full size
              </button>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={attemptImage}
              alt="Submitted ER diagram, full size"
              style={{ display: 'block', background: '#fff', margin: '0 auto' }}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}

        {/* Off screen, but real pixels: draw.io exports a blank image from a hidden
            or zero-sized frame. Kept mounted so the first attempt opened does not
            wait for a cold iframe. */}
        <iframe
          ref={rendererFrameRef}
          src={DRAWIO_RENDERER_URL}
          title="Diagram renderer"
          style={OFFSCREEN_FRAME_STYLE}
        />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
