'use client';

import { useEffect, useMemo } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Alert, Container, Group, Loader, Button } from '@mantine/core';
import { IconAlertCircle, IconArrowLeft } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { ERDiagramWorkspace } from '@/components/ERDiagramWorkspace';
import type { ERDiagramWorkspaceQuestion } from '@/components/ERDiagramWorkspace';
import { UserRole } from '@/types/user.types';
import { erDiagramService } from '@/services/er-diagram.service';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { queryKeys } from '@/services/query-keys';

export default function AssessmentErQuestionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const assessmentId = Number(params.id);
  const itemId = Number(params.itemId);
  const resourceId = Number(searchParams.get('resourceId'));
  const weight = Number(searchParams.get('weight')) || undefined;
  const backUrl = `/student/assessments/${assessmentId}/overview`;

  useEffect(() => {
    if (assessmentId && itemId) {
      studentAssessmentService.visitItem(assessmentId, itemId).catch(() => {
        // Non-critical — ignore errors
      });
    }
  }, [assessmentId, itemId]);

  // Static question content — cached (see providers.tsx) so returning to this item
  // during the assessment renders instantly without re-fetching.
  const questionQuery = useQuery({
    queryKey: queryKeys.erQuestionById(resourceId),
    queryFn: () => erDiagramService.getQuestionById(resourceId),
    enabled: !!resourceId,
  });

  const question = useMemo<ERDiagramWorkspaceQuestion | null>(() => {
    const data = questionQuery.data;
    if (!data) return null;
    return {
      id: data.id,
      title: data.title,
      description: data.problem_statement,
      difficulty: data.difficulty_label,
      rubric_md: data.rubric_md || '',
      rubric_json: data.rubric_json || null,
      show_rubric_on_attempt: data.show_rubric_on_attempt,
    };
  }, [questionQuery.data]);

  const loading = questionQuery.isLoading;
  const error = questionQuery.error
    ? ((questionQuery.error as { response?: { data?: { detail?: string } }; message?: string }).response?.data?.detail ||
        (questionQuery.error as { message?: string }).message ||
        'Failed to load question')
    : null;

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
      <ERDiagramWorkspace question={question} weight={weight} backUrl={backUrl} />
    </ProtectedRoute>
  );
}
