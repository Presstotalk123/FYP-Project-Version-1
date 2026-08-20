'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Title, Stack, Loader, Alert, Group, Badge } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { AssessmentForm } from '@/components/admin/AssessmentForm';
import { UserRole } from '@/types/user.types';
import { AssessmentDetail } from '@/types/assessment.types';
import { assessmentService } from '@/services/assessment.service';

export default function EditAssessmentPage() {
  const params = useParams();
  const id = Number(params.id);

  const [assessment, setAssessment] = useState<AssessmentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await assessmentService.getAssessmentById(id);
        setAssessment(data);
      } catch (err) {
        const e = err as { response?: { data?: { detail?: string } } };
        setError(e.response?.data?.detail || 'Failed to load assessment');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="md">
          <Group>
            <Title order={2}>Edit Assessment</Title>
            {assessment?.is_running && (
              <Badge color="blue" variant="light">Running — read-only</Badge>
            )}
            {assessment?.is_published && !assessment?.is_running && (
              <Badge color="yellow" variant="light">Published — questions frozen</Badge>
            )}
          </Group>

          {loading && (
            <Group justify="center" py="xl">
              <Loader size="lg" />
            </Group>
          )}

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {error}
            </Alert>
          )}

          {!loading && !error && assessment && (
            <AssessmentForm mode="edit" initial={assessment} />
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
