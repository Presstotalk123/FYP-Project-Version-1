'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Lab } from '@/types/lab.types';
import { labService } from '@/services/lab.service';

const IconPlay = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="5 3 19 12 5 21 5 3"/>
  </svg>
);
const IconEye = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
  </svg>
);

export default function StudentLabsPage() {
  const router = useRouter();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchLabs(); }, []);

  const fetchLabs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await labService.getLabs();
      setLabs(data);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load labs');
    } finally {
      setLoading(false);
    }
  };

  const handleLabAction = (lab: Lab) => {
    if (lab.is_running) {
      router.push(`/student/labs/${lab.id}/workspace`);
    } else {
      router.push(`/student/labs/${lab.id}/preview`);
    }
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <div className="page-head">
          <div>
            <h2>Database Labs</h2>
            <p>Join a running lab or preview the schema of an upcoming one.</p>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading labs…</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {/* Empty */}
        {!loading && !error && labs.length === 0 && (
          <div className="da-alert alert-info">
            <strong>No Labs Available</strong>
            <span>No labs are currently published. Check back later!</span>
          </div>
        )}

        {/* Lab cards */}
        {!loading && !error && labs.length > 0 && (
          <div className="grid-3">
            {labs.map((lab) => (
              <article key={lab.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <div className="button-row" style={{ marginBottom: 8 }}>
                    <h3 style={{ margin: 0, fontSize: 16 }}>{lab.title}</h3>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <span className={`badge ${lab.is_running ? 'badge-success' : 'badge-warn'}`}>
                        {lab.is_running ? 'Available' : 'Preview Only'}
                      </span>
                      {lab.lab_type === 'graph' && (
                        <span className="badge brand-badge">Graph</span>
                      )}
                    </div>
                  </div>
                  <p style={{ fontSize: 14, color: 'var(--text-muted)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {lab.description}
                  </p>
                </div>

                <button
                  className={`btn ${lab.is_running ? 'btn-brand' : 'btn-secondary'}`}
                  onClick={() => handleLabAction(lab)}
                  style={{ width: '100%', marginTop: 'auto' }}
                >
                  {lab.is_running ? <IconPlay /> : <IconEye />}
                  {lab.is_running ? 'Start Lab' : 'Preview Schema'}
                </button>

                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Created {new Date(lab.created_at).toLocaleDateString()}
                </span>
              </article>
            ))}
          </div>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
