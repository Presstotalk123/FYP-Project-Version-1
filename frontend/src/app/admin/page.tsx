'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { questionService } from '@/services/question.service';
import api from '@/services/api.service';

interface Stats {
  totalQuestions: number;
  totalStudents: number;
  totalAttempts: number;
}

export default function AdminDashboard() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats>({ totalQuestions: 0, totalStudents: 0, totalAttempts: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        const questions = await questionService.getQuestions();

        let studentCount = 0;
        try {
          const usersResponse = await api.get('/users');
          studentCount = usersResponse.data.filter((u: { role: string }) => u.role === 'student').length;
        } catch {
          studentCount = 0;
        }

        let attemptCount = 0;
        try {
          const attemptsResponse = await api.get('/attempts');
          attemptCount = attemptsResponse.data.length;
        } catch {
          attemptCount = 0;
        }

        setStats({
          totalQuestions: questions.length,
          totalStudents: studentCount,
          totalAttempts: attemptCount,
        });
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>Admin Dashboard</h2>
            <p>Welcome to the SQL Learning Platform administration panel.</p>
          </div>
        </div>

        {loading ? (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading stats…</span>
          </div>
        ) : (
          <>
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
