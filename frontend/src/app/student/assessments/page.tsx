'use client';

import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  Title,
  Stack,
  Card,
  Text,
  Badge,
  Button,
  Group,
  Loader,
  Alert,
  SimpleGrid,
} from '@mantine/core';
import { IconAlertCircle, IconClipboardList, IconPlayerPlay, IconClock, IconRefresh } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { queryKeys } from '@/services/query-keys';

export default function StudentAssessmentsPage() {
  const router = useRouter();

  // Session-cached (see providers.tsx). Invalidated after submitting an
  // assessment (see the overview page) so the list reflects the new status.
  const assessmentsQuery = useQuery({
    queryKey: queryKeys.studentAssessments,
    queryFn: () => studentAssessmentService.list(),
  });
  const assessments = assessmentsQuery.data ?? [];
  const loading = assessmentsQuery.isLoading;
  const error = assessmentsQuery.error
    ? ((assessmentsQuery.error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to load assessments')
    : null;
  const refreshing = assessmentsQuery.isFetching;
  const refresh = () => assessmentsQuery.refetch();

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <Stack gap="md">
          <Group justify="space-between" align="center">
            <Title order={2}>Assessments</Title>
            <Button
              variant="default"
              leftSection={<IconRefresh size={16} />}
              loading={refreshing}
              onClick={refresh}
              title="Reload latest data from the server"
            >
              Refresh
            </Button>
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

          {!loading && !error && assessments.length === 0 && (
            <Alert icon={<IconAlertCircle size={16} />} color="blue" title="No Assessments">
              No assessments are currently available. Check back later!
            </Alert>
          )}

          {!loading && !error && assessments.length > 0 && (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
              {assessments.map((assessment) => (
                <Card key={assessment.id} shadow="sm" padding="lg" radius="md" withBorder>
                  <Stack gap="md">
                    <div>
                      <Group justify="space-between" mb="xs">
                        <Text fw={600} size="lg">
                          {assessment.title}
                        </Text>
                        <Badge
                          color={assessment.is_running ? 'green' : 'yellow'}
                          size="sm"
                          leftSection={
                            assessment.is_running
                              ? <IconPlayerPlay size={12} />
                              : <IconClock size={12} />
                          }
                        >
                          {assessment.is_running ? 'Live' : 'Not Started'}
                        </Badge>
                      </Group>
                      <Text size="sm" c="dimmed" lineClamp={3}>
                        {assessment.description || 'No description provided.'}
                      </Text>
                    </div>

                    <Button
                      fullWidth
                      leftSection={<IconClipboardList size={16} />}
                      color="blue"
                      variant={assessment.is_running ? 'filled' : 'light'}
                      onClick={() => router.push(`/student/assessments/${assessment.id}`)}
                    >
                      View Assessment
                    </Button>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
