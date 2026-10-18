'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { sqlAnalyticsService } from '@/services/sql-analytics.service';
import type { SqlClassOverview } from '@/types/sql-analytics.types';

const rate = (v: number): string => `${Math.round(v * 100)}%`;

export default function SqlClassOverviewPage() {
  const router = useRouter();
  const [classGroup, setClassGroup] = useState<string>('');
  const [classGroups, setClassGroups] = useState<string[]>([]);
  const [data, setData] = useState<SqlClassOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    sqlAnalyticsService.classGroups().then(setClassGroups).catch(() => setClassGroups([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    sqlAnalyticsService
      .overview(classGroup || undefined)
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
  }, [classGroup]);

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>SQL Class Overview</h2>
            <p>Where the cohort struggles across all SQL practice questions.</p>
          </div>
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
            <h3>Weakness by concept</h3>
            <p style={{ color: 'var(--text-muted)', marginTop: 0 }}>
              Share of attempted questions a student never completed, per concept — weakest first.
            </p>
            {data.concepts.length === 0 ? (
              <p style={{ color: 'var(--text-muted)' }}>No tagged concept activity yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="da-table">
                  <thead><tr><th>Concept</th><th>Category</th><th>Not completed</th><th>Students</th><th>Questions</th></tr></thead>
                  <tbody>
                    {data.concepts.map((c) => (
                      <tr key={c.concept_id}>
                        <td>{c.display_name}</td>
                        <td>{c.category}</td>
                        <td>{rate(c.not_completed_rate)}</td>
                        <td>{c.students}</td>
                        <td>{c.questions}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <h3 style={{ marginTop: 24 }}>Questions</h3>
            <div className="table-wrap">
              <table className="da-table">
                <thead><tr><th>Question</th><th>Attempts</th><th>Students</th><th>Completion</th></tr></thead>
                <tbody>
                  {data.questions.map((q) => (
                    <tr
                      key={q.question_id}
                      onClick={() => router.push(`/admin/sql-analytics/${q.question_id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>{q.title}</td>
                      <td>{q.attempts}</td>
                      <td>{q.students}</td>
                      <td>{rate(q.completion_rate)}</td>
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
