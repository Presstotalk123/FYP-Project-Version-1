'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { StudentAttemptsModal } from '@/components/admin/StudentAttemptsModal';
import { UserRole } from '@/types/user.types';
import { Lab } from '@/types/lab.types';
import { labService } from '@/services/lab.service';

/* ── SVG icons ── */
const IconPlus = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);
const IconPublish = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
  </svg>
);
const IconEyeOff = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
);
const IconPlay = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="5 3 19 12 5 21 5 3"/>
  </svg>
);
const IconStop = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
  </svg>
);
const IconMessageOff = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h9"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
);
const IconMessageCheck = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z"/>
  </svg>
);
const IconReview = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
  </svg>
);
const IconEdit = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
  </svg>
);
const IconTrash = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="3 6 5 6 21 6"/>
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
    <path d="M10 11v6"/><path d="M14 11v6"/>
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
  </svg>
);

export default function AdminLabsPage() {
  const router = useRouter();
  const [labs, setLabs] = useState<Lab[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [labToDelete, setLabToDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [studentAttemptsModalOpen, setStudentAttemptsModalOpen] = useState(false);
  const [selectedLabForAttempts, setSelectedLabForAttempts] = useState<{ id: number; title: string } | null>(null);

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

  const handleDelete = async () => {
    if (!labToDelete) return;
    setDeleting(true);
    try {
      await labService.deleteLab(labToDelete);
      notifications.show({ title: 'Success', message: 'Lab deleted successfully', color: 'green' });
      setDeleteModalOpen(false);
      setLabToDelete(null);
      fetchLabs();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({ title: 'Error', message: e.response?.data?.detail || 'Failed to delete lab', color: 'red' });
    } finally {
      setDeleting(false);
    }
  };

  const handlePublish = async (labId: number, isPublished: boolean) => {
    try {
      if (isPublished) {
        await labService.unpublishLab(labId);
        notifications.show({ title: 'Success', message: 'Lab unpublished successfully', color: 'green' });
      } else {
        await labService.publishLab(labId);
        notifications.show({ title: 'Success', message: 'Lab published successfully', color: 'green' });
      }
      fetchLabs();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({ title: 'Error', message: e.response?.data?.detail || 'Failed to update lab', color: 'red' });
    }
  };

  const handleStartStop = async (labId: number, isRunning: boolean) => {
    try {
      if (isRunning) {
        const result = await labService.stopLab(labId);
        notifications.show({ title: 'Success', message: `Lab stopped. ${result.sessions_terminated} sessions terminated.`, color: 'green' });
      } else {
        await labService.startLab(labId);
        notifications.show({ title: 'Success', message: 'Lab started successfully', color: 'green' });
      }
      fetchLabs();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({ title: 'Error', message: e.response?.data?.detail || 'Failed to update lab', color: 'red' });
    }
  };

  const handleToggleResults = async (labId: number, hideCorrectness: boolean) => {
    try {
      if (hideCorrectness) {
        await labService.showLabResults(labId);
        notifications.show({ title: 'Success', message: 'Correctness feedback re-enabled for students', color: 'green' });
      } else {
        await labService.hideLabResults(labId);
        notifications.show({ title: 'Success', message: 'Correctness feedback hidden from students', color: 'green' });
      }
      fetchLabs();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({ title: 'Error', message: e.response?.data?.detail || 'Failed to update lab', color: 'red' });
    }
  };

  const openDeleteModal = (labId: number) => {
    setLabToDelete(labId);
    setDeleteModalOpen(true);
  };

  const handleViewStudentAttempts = (labId: number, labTitle: string) => {
    setSelectedLabForAttempts({ id: labId, title: labTitle });
    setStudentAttemptsModalOpen(true);
  };

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        {/* Header */}
        <div className="page-head">
          <div>
            <h2>Labs Management</h2>
            <p>Create and control SQL and graph labs.</p>
          </div>
          <div className="button-row">
            <button className="btn btn-secondary" onClick={() => router.push('/admin/labs/wizard?type=graph')}>
              <IconPlus />
              Create Graph Lab
            </button>
            <button className="btn btn-brand" onClick={() => router.push('/admin/labs/wizard')}>
              <IconPlus />
              Create New Lab
            </button>
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
            <strong>No Labs</strong>
            <span>No labs found. Create your first lab to get started.</span>
          </div>
        )}

        {/* Labs table */}
        {!loading && !error && labs.length > 0 && (
          <div className="table-wrap">
            <table className="da-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Description</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {labs.map((lab) => (
                  <tr key={lab.id}>
                    <td style={{ fontWeight: 600 }}>{lab.title}</td>
                    <td style={{ color: 'var(--text-muted)', maxWidth: 220 }}>
                      <span style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {lab.description}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${lab.lab_type === 'graph' ? 'brand-badge' : 'badge-info'}`}>
                        {lab.lab_type === 'graph' ? 'Graph' : 'SQL'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <span className={`badge ${lab.is_published ? 'badge-success' : 'neutral'}`}>
                          {lab.is_published ? 'Published' : 'Unpublished'}
                        </span>
                        {lab.is_published && (
                          <span className={`badge ${lab.is_running ? 'badge-info' : 'badge-warn'}`}>
                            {lab.is_running ? 'Running' : 'Stopped'}
                          </span>
                        )}
                        {lab.hide_correctness && (
                          <span className="badge badge-warn">Results Hidden</span>
                        )}
                      </div>
                    </td>
                    <td>{new Date(lab.created_at).toLocaleDateString()}</td>
                    <td>
                      <div className="actions">
                        {/* Publish/Unpublish */}
                        <button
                          className="icon-btn"
                          title={lab.is_published ? 'Unpublish' : 'Publish'}
                          onClick={() => handlePublish(lab.id, lab.is_published)}
                          style={{ color: lab.is_published ? '#6b7280' : '#16a34a' }}
                        >
                          {lab.is_published ? <IconEyeOff /> : <IconPublish />}
                        </button>
                        {/* Hide/Show correctness results from students */}
                        <button
                          className="icon-btn"
                          title={lab.hide_correctness ? 'Show correctness results to students' : 'Hide correctness results from students'}
                          onClick={() => handleToggleResults(lab.id, lab.hide_correctness)}
                          style={{ color: lab.hide_correctness ? '#f59e0b' : '#6b7280' }}
                        >
                          {lab.hide_correctness ? <IconMessageOff /> : <IconMessageCheck />}
                        </button>
                        {/* Review / Student Attempts */}
                        <button
                          className="icon-btn"
                          title="View Student Attempts"
                          onClick={() => handleViewStudentAttempts(lab.id, lab.title)}
                          style={{ color: '#2563eb' }}
                        >
                          <IconReview />
                        </button>
                        {/* Start/Stop */}
                        {lab.is_published && (
                          <button
                            className="icon-btn"
                            title={lab.is_running ? 'Stop Lab' : 'Start Lab'}
                            onClick={() => handleStartStop(lab.id, lab.is_running)}
                            style={{ color: lab.is_running ? '#ef4444' : '#2563eb' }}
                          >
                            {lab.is_running ? <IconStop /> : <IconPlay />}
                          </button>
                        )}
                        {/* Edit */}
                        <button
                          className="icon-btn"
                          title="Edit Lab"
                          onClick={() => router.push(`/admin/labs/${lab.id}/wizard`)}
                          disabled={lab.is_running}
                          style={{ color: '#6366f1', opacity: lab.is_running ? 0.4 : 1 }}
                        >
                          <IconEdit />
                        </button>
                        {/* Delete */}
                        <button
                          className="icon-btn"
                          title="Delete Lab"
                          onClick={() => openDeleteModal(lab.id)}
                          style={{ color: '#ef4444' }}
                        >
                          <IconTrash />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Delete modal */}
        {deleteModalOpen && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="del-lab-title">
            <div className="modal">
              <h3 id="del-lab-title">Delete Lab</h3>
              <p>Are you sure you want to delete this lab? This action cannot be undone.</p>
              <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => setDeleteModalOpen(false)} disabled={deleting}>Cancel</button>
                <button className="btn btn-danger" onClick={handleDelete} disabled={deleting}>{deleting ? 'Deleting…' : 'Delete'}</button>
              </div>
            </div>
          </div>
        )}

        {/* Student Attempts modal (kept as Mantine — it's a complex nested component) */}
        {selectedLabForAttempts && (
          <StudentAttemptsModal
            opened={studentAttemptsModalOpen}
            onClose={() => setStudentAttemptsModalOpen(false)}
            labId={selectedLabForAttempts.id}
            labTitle={selectedLabForAttempts.title}
          />
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
