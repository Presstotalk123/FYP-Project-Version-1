'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Assessment } from '@/types/assessment.types';
import { assessmentService } from '@/services/assessment.service';

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
const IconUsers = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

export default function AdminAssessmentsPage() {
  const router = useRouter();

  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [assessmentToDelete, setAssessmentToDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchAssessments();
  }, []);

  const fetchAssessments = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await assessmentService.getAssessments();
      setAssessments(data);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load assessments');
    } finally {
      setLoading(false);
    }
  };

  const handlePublishToggle = async (id: number, isPublished: boolean) => {
    try {
      if (isPublished) {
        await assessmentService.unpublishAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment unpublished successfully', color: 'green' });
      } else {
        await assessmentService.publishAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment published successfully', color: 'green' });
      }
      fetchAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to update assessment',
        color: 'red',
      });
    }
  };

  const handleStartStop = async (id: number, isRunning: boolean) => {
    try {
      if (isRunning) {
        await assessmentService.stopAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment stopped successfully', color: 'green' });
      } else {
        await assessmentService.startAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment started successfully', color: 'green' });
      }
      fetchAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to update assessment',
        color: 'red',
      });
    }
  };

  const openDeleteModal = (id: number) => {
    setAssessmentToDelete(id);
    setDeleteModalOpen(true);
  };

  const handleDelete = async () => {
    if (!assessmentToDelete) return;
    setDeleting(true);
    try {
      await assessmentService.deleteAssessment(assessmentToDelete);
      notifications.show({ title: 'Success', message: 'Assessment deleted successfully', color: 'green' });
      setDeleteModalOpen(false);
      setAssessmentToDelete(null);
      fetchAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to delete assessment',
        color: 'red',
      });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        {/* Header */}
        <div className="page-head">
          <div>
            <h2>Assessments</h2>
            <p>Create and manage student assessments.</p>
          </div>
          <div className="button-row">
            <button className="btn btn-brand" onClick={() => router.push('/admin/assessments/new')}>
              <IconPlus />
              Create Assessment
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading assessments…</span>
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
        {!loading && !error && assessments.length === 0 && (
          <div className="da-alert alert-info">
            <strong>No Assessments</strong>
            <span>No assessments yet. Create your first one to get started.</span>
          </div>
        )}

        {/* Assessments table */}
        {!loading && !error && assessments.length > 0 && (
          <div className="table-wrap">
            <table className="da-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Description</th>
                  <th>Items</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {assessments.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontWeight: 600 }}>{a.title}</td>
                    <td style={{ color: 'var(--text-muted)', maxWidth: 220 }}>
                      <span style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {a.description || '—'}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge-info">{a.item_count}</span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <span className={`badge ${a.is_published ? 'badge-success' : 'neutral'}`}>
                          {a.is_published ? 'Published' : 'Unpublished'}
                        </span>
                        {a.is_published && (
                          <span className={`badge ${a.is_running ? 'badge-info' : 'badge-warn'}`}>
                            {a.is_running ? 'Running' : 'Stopped'}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>{new Date(a.created_at).toLocaleDateString()}</td>
                    <td>
                      <div className="actions">
                        {/* Publish/Unpublish */}
                        <button
                          className="icon-btn"
                          title={a.is_published ? 'Unpublish' : 'Publish'}
                          onClick={() => handlePublishToggle(a.id, a.is_published)}
                          style={{ color: a.is_published ? '#6b7280' : '#16a34a' }}
                        >
                          {a.is_published ? <IconEyeOff /> : <IconPublish />}
                        </button>
                        {/* Start/Stop */}
                        {a.is_published && (
                          <button
                            className="icon-btn"
                            title={a.is_running ? 'Stop' : 'Start'}
                            onClick={() => handleStartStop(a.id, a.is_running)}
                            style={{ color: a.is_running ? '#ef4444' : '#2563eb' }}
                          >
                            {a.is_running ? <IconStop /> : <IconPlay />}
                          </button>
                        )}
                        {/* View Students */}
                        <button
                          className="icon-btn"
                          title="View Students"
                          onClick={() => router.push(`/admin/assessments/${a.id}/students`)}
                          style={{ color: '#0d9488' }}
                        >
                          <IconUsers />
                        </button>
                        {/* Edit */}
                        <button
                          className="icon-btn"
                          title="Edit"
                          onClick={() => router.push(`/admin/assessments/${a.id}`)}
                          disabled={a.is_running}
                          style={{ color: '#6366f1', opacity: a.is_running ? 0.4 : 1 }}
                        >
                          <IconEdit />
                        </button>
                        {/* Delete */}
                        <button
                          className="icon-btn"
                          title="Delete"
                          onClick={() => openDeleteModal(a.id)}
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
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="del-assessment-title">
            <div className="modal">
              <h3 id="del-assessment-title">Delete Assessment</h3>
              <p>Are you sure you want to delete this assessment? This action cannot be undone.</p>
              <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => setDeleteModalOpen(false)} disabled={deleting}>Cancel</button>
                <button className="btn btn-danger" onClick={handleDelete} disabled={deleting}>{deleting ? 'Deleting…' : 'Delete'}</button>
              </div>
            </div>
          </div>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
