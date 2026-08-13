'use client';

import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { questionService } from '@/services/question.service';
import { queryKeys } from '@/services/query-keys';
import api from '@/services/api.service';
import { ActiveUsersCard } from '@/components/admin/ActiveUsersCard';

const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
  </svg>
);

export default function AdminDashboard() {
  const router = useRouter();

  // Cached session-wide (see providers.tsx). `questions` is shared with the
  // Problems page, so visiting both fetches it only once.
  const questionsQuery = useQuery({
    queryKey: queryKeys.questions,
    queryFn: () => questionService.getQuestions(),
  });
  const usersQuery = useQuery({
    queryKey: queryKeys.users,
    queryFn: async () => (await api.get('/users')).data as { role: string }[],
  });
  const attemptsQuery = useQuery({
    queryKey: queryKeys.attempts,
    queryFn: async () => (await api.get('/attempts')).data as unknown[],
  });

  const loading = questionsQuery.isLoading;
  const stats = {
    totalQuestions: questionsQuery.data?.length ?? 0,
    totalStudents: usersQuery.data?.filter((u) => u.role === 'student').length ?? 0,
    totalAttempts: attemptsQuery.data?.length ?? 0,
  };

  const refresh = () => {
    questionsQuery.refetch();
    usersQuery.refetch();
    attemptsQuery.refetch();
  };
  const refreshing = questionsQuery.isFetching || usersQuery.isFetching || attemptsQuery.isFetching;

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>Admin Dashboard</h2>
            <p>Welcome to the SQL Learning Platform administration panel.</p>
          </div>
          <div className="button-row">
            <button className="btn btn-secondary" onClick={refresh} disabled={refreshing} title="Reload latest data from the server">
              <IconRefresh />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading stats…</span>
          </div>
        ) : (
          <>
            <ActiveUsersCard />

            {/* Metric cards */}
            <div className="grid-3" style={{ marginBottom: 18 }}>
              <article className="card metric">
                <div>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Total Questions
                  </span>
                  <strong>{stats.totalQuestions}</strong>
                </div>
                <span className="badge brand-badge">SQL</span>
              </article>

              <article className="card metric">
                <div>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Registered Students
                  </span>
                  <strong>{stats.totalStudents}</strong>
                </div>
                <span className="badge badge-success">Students</span>
              </article>

              <article className="card metric">
                <div>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Total Attempts
                  </span>
                  <strong>{stats.totalAttempts}</strong>
                </div>
                <span className="badge badge-warn">Attempts</span>
              </article>
            </div>

            {/* Quick actions */}
            <article className="card">
              <h3 style={{ marginBottom: 14 }}>Quick Actions</h3>
              <div className="button-row">
                <button
                  className="btn btn-primary"
                  onClick={() => router.push('/admin/questions')}
                >
                  Manage Questions
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => router.push('/admin/questions/new')}
                >
                  Create New Question
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => router.push('/admin/labs')}
                >
                  Manage Labs
                </button>
              </div>
            </article>
          </>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
