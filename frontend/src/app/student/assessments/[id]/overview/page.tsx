'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Title,
  Text,
  Stack,
  Button,
  Group,
  Loader,
  Alert,
  Badge,
  Card,
  Grid,
  Modal,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconAlertCircle,
  IconArrowLeft,
  IconCheck,
  IconCode,
  IconDatabase,
  IconTopologyComplex,
  IconLogout,
} from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { StudentAssessmentDetail, StudentAssessmentItemView, AssessmentItemType } from '@/types/assessment.types';
import { studentAssessmentService } from '@/services/studentAssessment.service';
import { AssessmentTimer } from '@/components/assessment/AssessmentTimer';
import { QuestionWeightBadge } from '@/components/assessment/QuestionWeightBadge';

function itemTypeLabel(type: AssessmentItemType): string {
  switch (type) {
    case 'sql_question': return 'SQL';
    case 'er_question':  return 'ER Diagram';
    case 'sql_lab':      return 'SQL Lab';
    case 'graph_lab':    return 'Graph Lab';
  }
}

function itemTypeColor(type: AssessmentItemType): string {
  switch (type) {
    case 'sql_question': return 'blue';
    case 'er_question':  return 'violet';
    case 'sql_lab':      return 'teal';
    case 'graph_lab':    return 'grape';
  }
}

function itemTypeIcon(type: AssessmentItemType) {
  switch (type) {
    case 'sql_question': return <IconCode size={20} />;
    case 'er_question':  return <IconTopologyComplex size={20} />;
    case 'sql_lab':      return <IconDatabase size={20} />;
    case 'graph_lab':    return <IconDatabase size={20} />;
  }
}

function itemWorkspaceUrl(assessmentId: number, item: StudentAssessmentItemView): string {
  const base = `/student/assessments/${assessmentId}/items/${item.id}`;
  // weight is carried in the URL (like resourceId) so the workspace can show it
  // without a second fetch. Display-only, so URL-passing is safe here.
  const rid = `?resourceId=${item.item_id}&weight=${item.weight}`;
  switch (item.item_type) {
    case 'sql_question': return `${base}/sql-question${rid}`;
    case 'sql_lab':      return `${base}/sql-lab${rid}`;
    case 'graph_lab':    return `${base}/graph-lab${rid}`;
    case 'er_question':  return `${base}/er-question${rid}`;
  }
}

export default function AssessmentOverviewPage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = Number(params.id);

  const [assessment, setAssessment] = useState<StudentAssessmentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpened, { open: openConfirm, close: closeConfirm }] = useDisclosure(false);

  useEffect(() => {
    fetchData();
  }, [assessmentId]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Guard: must have an active session
      try {
        await studentAssessmentService.getSession(assessmentId);
      } catch {
        router.replace(`/student/assessments/${assessmentId}`);
        return;
      }

      const detail = await studentAssessmentService.getDetail(assessmentId);
      setAssessment(detail);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load assessment');
    } finally {
      setLoading(false);
    }
  };

  const handleItemClick = (item: StudentAssessmentItemView) => {
    router.push(itemWorkspaceUrl(assessmentId, item));
  };

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      await studentAssessmentService.submit(assessmentId);
      router.push('/student/assessments');
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to submit assessment');
      setSubmitting(false);
      closeConfirm();
    }
  };

  const attemptedCount = assessment?.items.filter((i) => i.visited).length ?? 0;
  const totalCount = assessment?.items.length ?? 0;

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <Stack gap="md">
          <Group justify="space-between">
            <Group>
              <Button
                variant="subtle"
                leftSection={<IconArrowLeft size={16} />}
                onClick={() => router.push(`/student/assessments/${assessmentId}`)}
                size="sm"
              >
                Back
              </Button>
              {assessment && <Title order={2}>{assessment.title}</Title>}
            </Group>
            <Group gap="sm">
              <AssessmentTimer />
              <Button
                color="red"
                leftSection={<IconLogout size={16} />}
                onClick={openConfirm}
              >
                End &amp; Submit
              </Button>
            </Group>
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
            <Stack gap="md">
              <Text c="dimmed" size="sm">
                {attemptedCount} of {totalCount} question{totalCount !== 1 ? 's' : ''} attempted
              </Text>

              <Grid>
                {assessment.items.map((item, index) => (
                  <Grid.Col key={item.id} span={{ base: 12, sm: 6, md: 4 }}>
                    <Card
                      shadow="sm"
                      padding="md"
                      radius="md"
                      withBorder
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleItemClick(item)}
                    >
                      <Stack gap="xs">
                        <Group justify="space-between">
                          <Text size="xs" c="dimmed" fw={600}>
                            Q{index + 1}
                          </Text>
                          <Group gap="xs">
                            <Badge color={itemTypeColor(item.item_type)} size="sm" variant="light">
                              {itemTypeLabel(item.item_type)}
                            </Badge>
                            {item.visited && (
                              <Badge color="green" size="sm" leftSection={<IconCheck size={10} />}>
                                Attempted
                              </Badge>
                            )}
                          </Group>
                        </Group>

                        <Group gap="xs">
                          {itemTypeIcon(item.item_type)}
                          <Text fw={500} size="sm" lineClamp={2} style={{ flex: 1 }}>
                            {item.item_title}
                          </Text>
                        </Group>

                        <QuestionWeightBadge weight={item.weight} size="sm" />
                      </Stack>
                    </Card>
                  </Grid.Col>
                ))}
              </Grid>
            </Stack>
          )}
        </Stack>

        <Modal
          opened={confirmOpened}
          onClose={closeConfirm}
          title="Submit Assessment"
          centered
        >
          <Stack gap="md">
            <Text>
              Are you sure you want to end and submit this assessment? You will not be able to attempt any more questions after submitting.
            </Text>
            <Text size="sm" c="dimmed">
              {attemptedCount} of {totalCount} question{totalCount !== 1 ? 's' : ''} attempted.
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={closeConfirm}>
                Cancel
              </Button>
              <Button color="red" loading={submitting} onClick={handleSubmit}>
                Submit Assessment
              </Button>
            </Group>
          </Stack>
        </Modal>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
