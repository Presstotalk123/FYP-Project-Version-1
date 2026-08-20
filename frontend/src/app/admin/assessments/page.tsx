'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { assessmentService } from '@/services/assessment.service';
import { queryKeys } from '@/services/query-keys';

/* ── SVG icons ── */
const IconPlus = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);
const IconRefresh = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
  </svg>
);
const IconPublish = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
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
const IconKey = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
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
  const queryClient = useQueryClient();

  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [assessmentToDelete, setAssessmentToDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [stopModalOpen, setStopModalOpen] = useState(false);
  const [assessmentToStop, setAssessmentToStop] = useState<number | null>(null);
  const [stopping, setStopping] = useState(false);
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const [assessmentToPublish, setAssessmentToPublish] = useState<number | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [passcodeModalOpen, setPasscodeModalOpen] = useState(false);
  const [assessmentForPasscode, setAssessmentForPasscode] = useState<number | null>(null);
  const [assessmentForPasscodeHasPw, setAssessmentForPasscodeHasPw] = useState(false);
  const [passcodeValue, setPasscodeValue] = useState('');
  const [clearPasscode, setClearPasscode] = useState(false);
  const [savingPasscode, setSavingPasscode] = useState(false);
  const [loadingPasscode, setLoadingPasscode] = useState(false);

  // Session-cached (see providers.tsx): revisiting this page serves cache, no refetch.
  const assessmentsQuery = useQuery({ queryKey: queryKeys.assessments, queryFn: () => assessmentService.getAssessments() });
  const assessments = assessmentsQuery.data ?? [];
  const loading = assessmentsQuery.isLoading;
  const error = assessmentsQuery.error
    ? ((assessmentsQuery.error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load assessments')
    : null;
  const refreshing = assessmentsQuery.isFetching;
  const refresh = () => assessmentsQuery.refetch();

  // After a mutation, mark the cache stale so it re-fetches once.
  const invalidateAssessments = () => queryClient.invalidateQueries({ queryKey: queryKeys.assessments });

  const openPublishModal = (id: number) => {
    setAssessmentToPublish(id);
    setPublishModalOpen(true);
  };

  // Publishing is permanent: items are frozen and the assessment can no longer be
  // edited or unpublished. Confirm before firing.
  const handleConfirmPublish = async () => {
    if (assessmentToPublish === null) return;
    setPublishing(true);
    try {
      await assessmentService.publishAssessment(assessmentToPublish);
      notifications.show({ title: 'Success', message: 'Assessment published successfully', color: 'green' });
      setPublishModalOpen(false);
      setAssessmentToPublish(null);
      invalidateAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to publish assessment',
        color: 'red',
      });
    } finally {
      setPublishing(false);
    }
  };

  // The list only knows whether a passcode exists (has_password), not its value, so
  // fetch the full assessment detail (which does carry the plaintext passcode) to show
  // staff the current value instead of opening the field blank.
  const openPasscodeModal = async (id: number, hasPassword: boolean) => {
    setAssessmentForPasscode(id);
    setAssessmentForPasscodeHasPw(hasPassword);
    setPasscodeValue('');
    setClearPasscode(false);
    setPasscodeModalOpen(true);
    if (hasPassword) {
      setLoadingPasscode(true);
      try {
        const detail = await assessmentService.getAssessmentById(id);
        setPasscodeValue(detail.password ?? '');
      } catch (err) {
        const e = err as { response?: { data?: { detail?: string } } };
        notifications.show({
          title: 'Error',
          message: e.response?.data?.detail || 'Failed to load current passcode',
          color: 'red',
        });
      } finally {
        setLoadingPasscode(false);
      }
    }
  };

  // A published assessment's items are frozen; the passcode is not. Send a passcode-only
  // payload (no items/title/description) so the backend leaves the frozen items alone.
  const handleConfirmPasscode = async () => {
    if (assessmentForPasscode === null) return;
    setSavingPasscode(true);
    try {
      await assessmentService.updateAssessment(
        assessmentForPasscode,
        clearPasscode ? { clear_password: true } : { password: passcodeValue.trim() },
      );
      notifications.show({
        title: 'Success',
        message: clearPasscode ? 'Passcode removed' : 'Passcode updated',
        color: 'green',
      });
      setPasscodeModalOpen(false);
      setAssessmentForPasscode(null);
      invalidateAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to update passcode',
        color: 'red',
      });
    } finally {
      setSavingPasscode(false);
    }
  };

  const handleStart = async (id: number) => {
    try {
      await assessmentService.startAssessment(id);
      notifications.show({ title: 'Success', message: 'Assessment started successfully', color: 'green' });
      invalidateAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to update assessment',
        color: 'red',
      });
    }
  };

  const openStopModal = (id: number) => {
    setAssessmentToStop(id);
    setStopModalOpen(true);
  };

  // Stopping now force-ends & submits every active student, so confirm before firing.
  const handleConfirmStop = async () => {
    if (assessmentToStop === null) return;
    setStopping(true);
    try {
      await assessmentService.stopAssessment(assessmentToStop);
      notifications.show({ title: 'Success', message: 'Assessment stopped. All active students were submitted.', color: 'green' });
      setStopModalOpen(false);
      setAssessmentToStop(null);
      invalidateAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to stop assessment',
        color: 'red',
      });
    } finally {
      setStopping(false);
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
      invalidateAssessments();
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
            <button className="btn btn-secondary" onClick={refresh} disabled={refreshing} title="Reload latest data from the server">
              <IconRefresh />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
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
                        {a.is_published && a.gateway_enabled && (
                          <span className="badge badge-info" title="Access is driven by the per-class-group Timing Gateway schedule">
                            Scheduled
                          </span>
                        )}
                        {a.is_published && !a.gateway_enabled && (
                          <span className={`badge ${a.is_running ? 'badge-info' : 'badge-warn'}`}>
                            {a.is_running ? 'Running' : 'Stopped'}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>{new Date(a.created_at).toLocaleDateString()}</td>
                    <td>
                      <div className="actions">
                        {/* Publish (permanent — no unpublish once published) */}
                        {!a.is_published && (
                          <button
                            className="icon-btn"
                            title="Publish"
                            onClick={() => openPublishModal(a.id)}
                            style={{ color: '#16a34a' }}
                          >
                            <IconPublish />
                          </button>
                        )}
                        {/* Start/Stop — hidden when the Timing Gateway drives access on a schedule. */}
                        {a.is_published && !a.gateway_enabled && (
                          <button
                            className="icon-btn"
                            title={a.is_running ? 'Stop' : 'Start'}
                            onClick={() => (a.is_running ? openStopModal(a.id) : handleStart(a.id))}
                            style={{ color: a.is_running ? '#ef4444' : '#2563eb' }}
                          >
                            {a.is_running ? <IconStop /> : <IconPlay />}
                          </button>
                        )}
                        {/* Change passcode (published only; must be stopped) */}
                        {a.is_published && (
                          <button
                            className="icon-btn"
                            title={a.is_running ? 'Stop the assessment to change its passcode' : 'Change passcode'}
                            onClick={() => openPasscodeModal(a.id, a.has_password)}
                            disabled={a.is_running}
                            style={{ color: '#d97706', opacity: a.is_running ? 0.4 : 1 }}
                          >
                            <IconKey />
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
                        {/* Edit. Once published the question list is frozen, but title/
                            description/password/timing/gateway stay editable — so keep the
                            button (disabled while running, mirroring the passcode button). */}
                        <button
                          className="icon-btn"
                          title={
                            a.is_running
                              ? 'Stop the assessment to edit it'
                              : a.is_published
                                ? 'Edit (questions are frozen)'
                                : 'Edit'
                          }
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

        {/* Publish modal */}
        {publishModalOpen && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="publish-assessment-title">
            <div className="modal">
              <h3 id="publish-assessment-title">Publish Assessment</h3>
              <p>Once published, the <strong>question list is frozen</strong> for students and can no longer be changed, and the assessment can't be unpublished. You can still edit the title, description, password, and timing afterward. Make sure the questions are final before continuing.</p>
              <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => setPublishModalOpen(false)} disabled={publishing}>Cancel</button>
                <button className="btn btn-brand" onClick={handleConfirmPublish} disabled={publishing}>{publishing ? 'Publishing…' : 'Publish'}</button>
              </div>
            </div>
          </div>
        )}

        {/* Passcode modal */}
        {passcodeModalOpen && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="passcode-assessment-title">
            <div className="modal">
              <h3 id="passcode-assessment-title">Change Passcode</h3>
              <p style={{ color: 'var(--text-muted)' }}>
                {assessmentForPasscodeHasPw
                  ? 'This assessment currently has a passcode.'
                  : 'This assessment has no passcode.'}
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <input
                  type="text"
                  className="da-input"
                  placeholder={loadingPasscode ? 'Loading current passcode…' : 'New passcode'}
                  value={passcodeValue}
                  onChange={(e) => setPasscodeValue(e.target.value)}
                  disabled={clearPasscode || savingPasscode || loadingPasscode}
                  autoFocus
                />
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                  <input
                    type="checkbox"
                    checked={clearPasscode}
                    onChange={(e) => setClearPasscode(e.target.checked)}
                    disabled={savingPasscode}
                  />
                  Remove passcode (make assessment open)
                </label>
              </div>
              <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => setPasscodeModalOpen(false)} disabled={savingPasscode}>Cancel</button>
                <button
                  className="btn btn-brand"
                  onClick={handleConfirmPasscode}
                  disabled={savingPasscode || loadingPasscode || (!clearPasscode && !passcodeValue.trim())}
                >
                  {savingPasscode ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Stop modal */}
        {stopModalOpen && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="stop-assessment-title">
            <div className="modal">
              <h3 id="stop-assessment-title">Stop Assessment</h3>
              <p>This will immediately <strong>end and submit all active students</strong>, regardless of their time remaining. This cannot be undone.</p>
              <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => setStopModalOpen(false)} disabled={stopping}>Cancel</button>
                <button className="btn btn-danger" onClick={handleConfirmStop} disabled={stopping}>{stopping ? 'Stopping…' : 'Stop & Submit All'}</button>
              </div>
            </div>
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
