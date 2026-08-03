'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { QuestionForm } from '@/components/admin/QuestionForm';
import { UserRole } from '@/types/user.types';
import { QuestionDetail } from '@/types/question.types';
import { questionService } from '@/services/question.service';

export default function EditQuestionPage() {
  const params = useParams();
  const questionId = parseInt((params?.id as string) || '0');

  const [question, setQuestion] = useState<QuestionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchQuestion = async () => {
      try {
        setLoading(true);
        const data = await questionService.getQuestionById(questionId);
        setQuestion(data);
      } catch (err) {
        const error = err as { response?: { data?: { detail?: string } } };
        setError(error.response?.data?.detail || 'Failed to load question');
      } finally {
        setLoading(false);
      }
    };

    fetchQuestion();
  }, [questionId]);

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          {loading && (
            <div className="loading-center">
              <div className="spinner" />
              <span>Loading question…</span>
            </div>
          )}

          {!loading && (error || !question) && (
            <div className="da-alert alert-error" role="alert">
              <strong>Error</strong>
              <span>{error || 'Question not found'}</span>
            </div>
          )}

          {!loading && !error && question && (
            <div className="card" style={{ padding: 28 }}>
              <h3 style={{ margin: '0 0 20px', fontSize: 20 }}>Edit Question</h3>
              <QuestionForm question={question} isEdit />
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
