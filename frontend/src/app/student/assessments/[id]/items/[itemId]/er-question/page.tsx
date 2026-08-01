'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { Alert, Container, Group, Loader, Button } from '@mantine/core';
import { IconAlertCircle, IconArrowLeft } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { ERDiagramWorkspace } from '@/components/ERDiagramWorkspace';
import type { ERDiagramWorkspaceQuestion } from '@/components/ERDiagramWorkspace';
import { UserRole } from '@/types/user.types';
import { erDiagramService } from '@/services/er-diagram.service';
import { studentAssessmentService } from '@/services/studentAssessment.service';

export default function AssessmentErQuestionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const assessmentId = Number(params.id);
  const itemId = Number(params.itemId);
  const resourceId = Number(searchParams.get('resourceId'));
  const weight = Number(searchParams.get('weight')) || undefined;
  const backUrl = `/student/assessments/${assessmentId}/overview`;

  const [question, setQuestion] = useState<ERDiagramWorkspaceQuestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (assessmentId && itemId) {
      studentAssessmentService.visitItem(assessmentId, itemId).catch(() => {
        // Non-critical — ignore errors
      });
    }
  }, [assessmentId, itemId]);

  useEffect(() => {
    const fetchQuestion = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await erDiagramService.getQuestionById(resourceId);
        setQuestion({
          id: data.id,
          title: data.title,
          description: data.problem_statement,
          difficulty: data.difficulty_label,
          rubric_md: data.rubric_md || '',
          rubric_json: data.rubric_json || null,
          show_rubric_on_attempt: data.show_rubric_on_attempt,
        });
      } catch (err) {
        const e = err as { response?: { data?: { detail?: string } }; message?: string };
        setError(e.response?.data?.detail || e.message || 'Failed to load question');
      } finally {
        setLoading(false);
      }
    };

    if (resourceId) fetchQuestion();
  }, [resourceId]);

  if (loading) {
    return (
      <ProtectedRoute requiredRole={UserRole.STUDENT}>
        <Container py="xl">
          <Group justify="center">
            <Loader />
          </Group>
        </Container>
      </ProtectedRoute>
    );
  }

  if (error || !question) {
    return (
      <ProtectedRoute requiredRole={UserRole.STUDENT}>
        <Container py="xl">
          <Button
            variant="subtle"
            leftSection={<IconArrowLeft size={16} />}
            onClick={() => router.push(backUrl)}
            mb="md"
          >
            Back to Assessment
          </Button>
          <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
            {error || 'Question not found'}
          </Alert>
        </Container>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <ERDiagramWorkspace question={question} weight={weight} />
    </ProtectedRoute>
  );
}
