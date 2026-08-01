'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Title,
  Button,
  Stack,
  Group,
  Table,
  Badge,
  Loader,
  Alert,
  Text,
  Drawer,
  Card,
  ScrollArea,
  Modal,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconAlertCircle,
  IconArrowLeft,
  IconActivity,
  IconEye,
  IconRefresh,
} from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import {
  AssessmentStudentRow,
  AssessmentStudentsResponse,
  AssessmentItemComponentScore,
  StudentComponentScoresResponse,
} from '@/types/assessment.types';
import { assessmentService } from '@/services/assessment.service';

export default function AssessmentStudentsPage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = Number(params.id);

  const [data, setData] = useState<AssessmentStudentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Activity drawer
  const [activityStudent, setActivityStudent] = useState<AssessmentStudentRow | null>(null);
  const [scores, setScores] = useState<StudentComponentScoresResponse | null>(null);
  const [scoresLoading, setScoresLoading] = useState(false);
  const [scoresError, setScoresError] = useState<string | null>(null);

  // Reset-attempt confirmation
  const [resetStudent, setResetStudent] = useState<AssessmentStudentRow | null>(null);
  const [resetting, setResetting] = useState(false);

  const fetchStudents = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await assessmentService.getAssessmentStudents(assessmentId);
      setData(result);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load students');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStudents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  const handleResetConfirm = async () => {
    if (!resetStudent) return;
    setResetting(true);
    try {
      await assessmentService.resetStudentAttempt(assessmentId, resetStudent.user_id);
      notifications.show({
        color: 'green',
        title: 'Attempt reset',
        message: `${resetStudent.email} has a clean slate and can retake this assessment.`,
      });
      setResetStudent(null);
      await fetchStudents();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        color: 'red',
        title: 'Reset failed',
        message: e.response?.data?.detail || 'Could not reset the attempt.',
      });
    } finally {
      setResetting(false);
    }
  };

  const openActivityDrawer = async (student: AssessmentStudentRow) => {
    setActivityStudent(student);
    setScores(null);
    setScoresError(null);
    setScoresLoading(true);
    try {
      const result = await assessmentService.getStudentComponentScores(assessmentId, student.user_id);
      setScores(result);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setScoresError(e.response?.data?.detail || 'Failed to load scores');
    } finally {
      setScoresLoading(false);
    }
  };

  const closeActivityDrawer = () => {
    setActivityStudent(null);
    setScores(null);
    setScoresError(null);
  };

  const itemTypeBadgeColor: Record<string, string> = {
    sql_question: 'blue',
    er_question: 'violet',
    sql_lab: 'orange',
    graph_lab: 'teal',
  };

  const itemTypeLabel: Record<string, string> = {
    sql_question: 'SQL Question',
    er_question: 'ER Question',
    sql_lab: 'SQL Lab',
    graph_lab: 'Graph Lab',
  };

  const renderItemScore = (item: AssessmentItemComponentScore, studentId: number) => {
    if (item.item_type === 'sql_question') {
      const correct = item.has_correct_attempt;
      const count = item.attempt_count ?? 0;
      return (
        <Group gap="xs">
          <Badge color={correct ? 'green' : count > 0 ? 'red' : 'gray'} variant="light">
            {correct ? 'Solved' : count > 0 ? 'Not Solved' : 'Not Attempted'}
          </Badge>
          {count > 0 && (
            <Text size="sm" c="dimmed">{count} attempt{count !== 1 ? 's' : ''}</Text>
          )}
        </Group>
      );
    }

    if (item.item_type === 'er_question') {
      return (
        <Badge color={item.visited ? 'blue' : 'gray'} variant="light">
          {item.visited ? 'Visited' : 'Not Visited'}
        </Badge>
      );
    }

    if (item.item_type === 'sql_lab' || item.item_type === 'graph_lab') {
      const correct = item.tasks_correct ?? 0;
      const total = item.tasks_total ?? 0;
      const allDone = total > 0 && correct === total;
      return (
        <Group gap="xs">
          <Badge color={allDone ? 'green' : correct > 0 ? 'yellow' : 'gray'} variant="light">
            {correct}/{total} tasks
          </Badge>
          <Button
            size="xs"
            variant="light"
            color="teal"
            leftSection={<IconEye size={12} />}
            onClick={() => router.push(`/admin/labs/${item.item_id}/review/${studentId}`)}
          >
            View Lab Activity
          </Button>
        </Group>
      );
    }

    return <Text size="sm" c="dimmed">—</Text>;
  };

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="md">
          <Group>
            <Button
              variant="subtle"
              leftSection={<IconArrowLeft size={16} />}
              onClick={() => router.push('/admin/assessments')}
            >
              Back
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

          {data && (
            <>
              <Title order={2}>
                &ldquo;{data.assessment_title}&rdquo; — Student Activity
              </Title>

              {data.students.length === 0 ? (
                <Alert icon={<IconAlertCircle size={16} />} color="blue" title="No Students">
                  No students have joined this assessment yet.
                </Alert>
              ) : (
                <Table striped highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Email</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Joined At</Table.Th>
                      <Table.Th>Submitted At</Table.Th>
                      <Table.Th>Actions</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.students.map((student) => (
                      <Table.Tr key={student.user_id}>
                        <Table.Td>
                          <Text size="sm" fw={500}>{student.email}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge color={student.is_active ? 'blue' : 'green'} variant="light">
                            {student.is_active ? 'Active' : 'Submitted'}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{new Date(student.joined_at).toLocaleString()}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {student.submitted_at
                              ? new Date(student.submitted_at).toLocaleString()
                              : '—'}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <Button
                              size="xs"
                              variant="light"
                              color="teal"
                              leftSection={<IconActivity size={14} />}
                              onClick={() => openActivityDrawer(student)}
                            >
                              View Activity
                            </Button>
                            <Button
                              size="xs"
                              variant="light"
                              color="red"
                              leftSection={<IconRefresh size={14} />}
                              onClick={() => setResetStudent(student)}
                            >
                              Reset
                            </Button>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </>
          )}
        </Stack>

        {/* Reset-attempt confirmation */}
        <Modal
          opened={!!resetStudent}
          onClose={() => (resetting ? null : setResetStudent(null))}
          title={<Text fw={600}>Reset attempt?</Text>}
          centered
        >
          <Stack gap="md">
            <Text size="sm">
              This permanently erases <b>{resetStudent?.email}</b>&rsquo;s work on this assessment
              (all submissions, query history, and progress) and removes their session, giving them a
              clean slate to retake it. Their standalone practice is not affected. This cannot be undone.
            </Text>
            <Group justify="flex-end" gap="sm">
              <Button variant="default" onClick={() => setResetStudent(null)} disabled={resetting}>
                Cancel
              </Button>
              <Button color="red" loading={resetting} onClick={handleResetConfirm}>
                Reset attempt
              </Button>
            </Group>
          </Stack>
        </Modal>

        {/* Component-wise activity drawer */}
        <Drawer
          opened={!!activityStudent}
          onClose={closeActivityDrawer}
          title={
            <Text fw={600}>
              Activity — {activityStudent?.email}
            </Text>
          }
          position="right"
          size="lg"
          scrollAreaComponent={ScrollArea.Autosize}
        >
          {scoresLoading && (
            <Group justify="center" py="xl">
              <Loader />
            </Group>
          )}

          {scoresError && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {scoresError}
            </Alert>
          )}

          {scores && (
            <Stack gap="sm">
              {scores.items.map((item, idx) => (
                <Card key={item.assessment_item_id} withBorder padding="sm" radius="md">
                  <Group justify="space-between" align="flex-start" wrap="nowrap">
                    <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
                      <Group gap="xs">
                        <Text size="xs" c="dimmed" fw={500}>#{idx + 1}</Text>
                        <Badge
                          size="xs"
                          color={itemTypeBadgeColor[item.item_type] ?? 'gray'}
                          variant="filled"
                        >
                          {itemTypeLabel[item.item_type] ?? item.item_type}
                        </Badge>
                      </Group>
                      <Text size="sm" fw={500} lineClamp={2}>{item.item_title}</Text>
                    </Stack>
                    <Stack gap={4} align="flex-end">
                      {renderItemScore(item, activityStudent!.user_id)}
                    </Stack>
                  </Group>
                </Card>
              ))}
            </Stack>
          )}
        </Drawer>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
