'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Container, Loader, Stack, Text, Alert } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
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
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Container size="lg">
          {loading ? (
            <Stack align="center" justify="center" style={{ minHeight: '300px' }}>
              <Loader size="lg" />
              <Text c="dimmed">Loading question...</Text>
            </Stack>
          ) : error || !question ? (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {error || 'Question not found'}
            </Alert>
          ) : (
            <QuestionForm question={question} isEdit />
          )}
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
