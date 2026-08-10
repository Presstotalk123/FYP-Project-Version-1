'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Question } from '@/types/question.types';
import { questionService } from '@/services/question.service';
import api from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api.config';

const difficultyClass: Record<string, string> = {
  easy: 'easy',
  medium: 'medium',
  hard: 'hard',
};

/* ─── SVG icons ─── */
const IconPlus = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
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
const IconChart = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
  </svg>
);

export default function AdminQuestionsPage() {
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [questionToDelete, setQuestionToDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => { fetchQuestions(); }, []);

  const fetchQuestions = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await questionService.getQuestions();
      setQuestions(data);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load questions');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!questionToDelete) return;
    setDeleting(true);
    try {
      await api.delete(API_ENDPOINTS.QUESTIONS.DETAIL(questionToDelete));
      notifications.show({ title: 'Success', message: 'Question deleted successfully', color: 'green' });
      setDeleteModalOpen(false);
      setQuestionToDelete(null);
      fetchQuestions();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({ title: 'Error', message: e.response?.data?.detail || 'Failed to delete question', color: 'red' });
    } finally {
      setDeleting(false);
    }
  };

  const openDeleteModal = (questionId: number) => {
    setQuestionToDelete(questionId);
    setDeleteModalOpen(true);
  };

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        {/* Header */}
        <div className="page-head">
          <div>
            <h2>Manage Questions</h2>
            <p>Create, edit, and manage SQL practice questions</p>
          </div>
          <button
            className="btn btn-brand"
            onClick={() => router.push('/admin/questions/new')}
          >
            <IconPlus />
            Create Question
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="loading-center">
            <div className="spinner" />
            <span>Loading questions…</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {/* Questions table */}
        {!loading && !error && (
          questions.length === 0 ? (
            <div className="da-alert alert-info">
              <strong>No questions yet</strong>
              <span>Click &quot;Create Question&quot; to add the first one.</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="da-table">
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>ID</th>
                    <th>Title</th>
                    <th style={{ width: 120 }}>Difficulty</th>
                    <th style={{ width: 130 }}>Created At</th>
                    <th style={{ width: 90 }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {questions.map((q) => (
                    <tr key={q.id}>
                      <td>{q.id}</td>
                      <td>{q.title}</td>
                      <td>
                        <span className={`badge ${difficultyClass[q.difficulty] || 'neutral'}`}>
                          {q.difficulty.charAt(0).toUpperCase() + q.difficulty.slice(1)}
                        </span>
                      </td>
                      <td>{new Date(q.created_at).toLocaleDateString()}</td>
                      <td>
                        <div className="actions">
                          <button
                            className="icon-btn"
                            title="Student analytics"
                            onClick={() => router.push(`/admin/sql-analytics/${q.id}`)}
                            style={{ color: '#7c3aed' }}
                          >
                            <IconChart />
                          </button>
                          <button
                            className="icon-btn"
                            title="Edit"
                            onClick={() => router.push(`/admin/questions/${q.id}`)}
                            style={{ color: '#2563eb' }}
                          >
                            <IconEdit />
                          </button>
                          <button
                            className="icon-btn"
                            title="Delete"
                            onClick={() => openDeleteModal(q.id)}
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
          )
        )}

        {/* Delete confirmation modal */}
        {deleteModalOpen && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
            <div className="modal">
              <h3 id="delete-modal-title">Delete Question</h3>
              <p>Are you sure you want to delete this question? This action cannot be undone.</p>
              <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => setDeleteModalOpen(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-danger"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
