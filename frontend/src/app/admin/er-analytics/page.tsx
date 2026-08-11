'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { erAnalyticsService } from '@/services/er-analytics.service';
import type { AnalyticsContext, ClassOverview } from '@/types/er-analytics.types';

const rate = (v: number): string => `${Math.round(v * 100)}%`;

export default function ErClassOverviewPage() {
  const router = useRouter();
  const [context, setContext] = useState<AnalyticsContext>('all');
  const [classGroup, setClassGroup] = useState<string>('');
  const [classGroups, setClassGroups] = useState<string[]>([]);
  const [data, setData] = useState<ClassOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    erAnalyticsService.classGroups().then(setClassGroups).catch(() => setClassGroups([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    erAnalyticsService
      .overview(context, classGroup || undefined)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setError('Failed to load overview');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [context, classGroup]);

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>ERD Class Overview</h2>
            <p>Where the cohort struggles across all ERD questions.</p>
          </div>
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
          {/* Problems, not the question list: analytics is reached from there,
              so it is where staff expect to come back to. */}
          <button className="btn btn-secondary" onClick={() => router.push('/admin/problems')}>
            Back to problems
          </button>
        </div>

        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {data && (
          <>
            <h3>Weakness by rubric dimension</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead><tr><th>Dimension</th><th>Fail rate</th><th>Partial rate</th><th>Checks evaluated</th></tr></thead>
                <tbody>
                  {data.dimensions.map((d) => (
                    <tr key={d.dimension}>
                      <td>{d.dimension}</td>
                      <td>{rate(d.fail_rate)}</td>
                      <td>{rate(d.partial_rate)}</td>
                      <td>{d.checks_evaluated}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginTop: 24 }}>Top failing checks</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead><tr><th>Question</th><th>Check</th><th>Dimension</th><th>Fail rate</th><th>Attempts</th></tr></thead>
                <tbody>
                  {data.top_failing_checks.map((c) => (
                    <tr
                      key={`${c.question_id}-${c.check_id}`}
                      onClick={() => router.push(`/admin/er-analytics/${c.question_id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>{c.question_title}</td>
                      <td>{c.check_id}</td>
                      <td>{c.dimension}</td>
                      <td>{rate(c.fail_rate)}</td>
                      <td>{c.attempts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginTop: 24 }}>What students ask Baloo about</h3>
            {data.query_topics.length === 0 ? (
              <p style={{ color: 'var(--text-muted)' }}>No tutor questions asked yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="da-table">
                  <thead><tr><th>Topic</th><th>Questions</th><th>Recent examples</th></tr></thead>
                  <tbody>
                    {data.query_topics.map((t) => (
                      <tr key={t.topic}>
                        <td>{t.topic}</td>
                        <td>{t.count}</td>
                        <td>
                          <details>
                            <summary style={{ cursor: 'pointer' }}>
                              {t.examples[0] ?? ''}
                            </summary>
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

            <h3 style={{ marginTop: 24 }}>Questions</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead><tr><th>Question</th><th>Attempts</th><th>Students</th><th>Avg score</th></tr></thead>
                <tbody>
                  {data.questions.map((q) => (
                    <tr key={q.question_id} onClick={() => router.push(`/admin/er-analytics/${q.question_id}`)} style={{ cursor: 'pointer' }}>
                      <td>{q.title}</td>
                      <td>{q.attempts}</td>
                      <td>{q.students}</td>
                      <td>{q.avg_percent === null ? '—' : `${Math.round(q.avg_percent)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
