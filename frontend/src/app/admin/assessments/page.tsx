'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Title,
  Button,
  Stack,
  Group,
  Table,
  Badge,
  ActionIcon,
  Loader,
  Alert,
  Text,
  Modal,
  Tooltip,
} from '@mantine/core';
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconAlertCircle,
  IconPlayerPlay,
  IconPlayerStop,
  IconEye,
  IconEyeOff,
  IconUsers,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Assessment } from '@/types/assessment.types';
import { assessmentService } from '@/services/assessment.service';

export default function AdminAssessmentsPage() {
  const router = useRouter();

  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [assessmentToDelete, setAssessmentToDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchAssessments();
  }, []);

  const fetchAssessments = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await assessmentService.getAssessments();
      setAssessments(data);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Failed to load assessments');
    } finally {
      setLoading(false);
    }
  };

  const handlePublishToggle = async (id: number, isPublished: boolean) => {
    try {
      if (isPublished) {
        await assessmentService.unpublishAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment unpublished', color: 'green' });
      } else {
        await assessmentService.publishAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment published', color: 'green' });
      }
      fetchAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to update assessment',
        color: 'red',
      });
    }
  };

  const handleStartStop = async (id: number, isRunning: boolean) => {
    try {
      if (isRunning) {
        await assessmentService.stopAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment stopped', color: 'green' });
      } else {
        await assessmentService.startAssessment(id);
        notifications.show({ title: 'Success', message: 'Assessment started', color: 'green' });
      }
      fetchAssessments();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to update assessment',
        color: 'red',
      });
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
      notifications.show({ title: 'Success', message: 'Assessment deleted', color: 'green' });
      setDeleteModalOpen(false);
      setAssessmentToDelete(null);
      fetchAssessments();
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
        <Stack gap="md">
          <Group justify="space-between">
            <Title order={2}>Assessments</Title>
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => router.push('/admin/assessments/new')}
            >
              Create Assessment
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
              No assessments yet. Create your first one to get started.
            </Alert>
          )}

          {!loading && !error && assessments.length > 0 && (
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Title</Table.Th>
                  <Table.Th>Description</Table.Th>
                  <Table.Th>Items</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Created</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {assessments.map((a) => (
                  <Table.Tr key={a.id}>
                    <Table.Td>
                      <Text fw={500}>{a.title}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={2}>
                        {a.description || '—'}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" color="blue">{a.item_count}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Badge color={a.is_published ? 'green' : 'gray'}>
                          {a.is_published ? 'Published' : 'Unpublished'}
                        </Badge>
                        {a.is_published && (
                          <Badge color={a.is_running ? 'blue' : 'yellow'}>
                            {a.is_running ? 'Running' : 'Stopped'}
                          </Badge>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{new Date(a.created_at).toLocaleDateString()}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Tooltip label={a.is_published ? 'Unpublish' : 'Publish'}>
                          <ActionIcon
                            color={a.is_published ? 'gray' : 'green'}
                            variant="light"
                            onClick={() => handlePublishToggle(a.id, a.is_published)}
                          >
                            {a.is_published ? <IconEyeOff size={16} /> : <IconEye size={16} />}
                          </ActionIcon>
                        </Tooltip>
                        {a.is_published && (
                          <Tooltip label={a.is_running ? 'Stop' : 'Start'}>
                            <ActionIcon
                              color={a.is_running ? 'red' : 'blue'}
                              variant="light"
                              onClick={() => handleStartStop(a.id, a.is_running)}
                            >
                              {a.is_running ? <IconPlayerStop size={16} /> : <IconPlayerPlay size={16} />}
                            </ActionIcon>
                          </Tooltip>
                        )}
                        <Tooltip label="View Students">
                          <ActionIcon
                            color="teal"
                            variant="light"
                            onClick={() => router.push(`/admin/assessments/${a.id}/students`)}
                          >
                            <IconUsers size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Edit">
                          <ActionIcon
                            color="blue"
                            variant="light"
                            onClick={() => router.push(`/admin/assessments/${a.id}`)}
                            disabled={a.is_running}
                          >
                            <IconEdit size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Delete">
                          <ActionIcon
                            color="red"
                            variant="light"
                            onClick={() => openDeleteModal(a.id)}
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>

        <Modal
          opened={deleteModalOpen}
          onClose={() => setDeleteModalOpen(false)}
          title="Delete Assessment"
        >
          <Stack>
            <Text>Are you sure you want to delete this assessment? This action cannot be undone.</Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setDeleteModalOpen(false)}>
                Cancel
              </Button>
              <Button color="red" onClick={handleDelete} loading={deleting}>
                Delete
              </Button>
            </Group>
          </Stack>
        </Modal>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
