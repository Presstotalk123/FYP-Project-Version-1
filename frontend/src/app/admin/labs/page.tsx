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
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Lab } from '@/types/lab.types';
import { labService } from '@/services/lab.service';

export default function AdminLabsPage() {
  const router = useRouter();

  const [labs, setLabs] = useState<Lab[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [labToDelete, setLabToDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchLabs();
  }, []);

  const fetchLabs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await labService.getLabs();
      setLabs(data);
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to load labs');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!labToDelete) return;

    setDeleting(true);
    try {
      await labService.deleteLab(labToDelete);
      notifications.show({
        title: 'Success',
        message: 'Lab deleted successfully',
        color: 'green',
      });
      setDeleteModalOpen(false);
      setLabToDelete(null);
      fetchLabs();
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to delete lab',
        color: 'red',
      });
    } finally {
      setDeleting(false);
    }
  };

  const handlePublish = async (labId: number, isPublished: boolean) => {
    try {
      if (isPublished) {
        await labService.unpublishLab(labId);
        notifications.show({
          title: 'Success',
          message: 'Lab unpublished successfully',
          color: 'green',
        });
      } else {
        await labService.publishLab(labId);
        notifications.show({
          title: 'Success',
          message: 'Lab published successfully',
          color: 'green',
        });
      }
      fetchLabs();
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to update lab',
        color: 'red',
      });
    }
  };

  const handleStartStop = async (labId: number, isRunning: boolean) => {
    try {
      if (isRunning) {
        const result = await labService.stopLab(labId);
        notifications.show({
          title: 'Success',
          message: `Lab stopped. ${result.sessions_terminated} sessions terminated.`,
          color: 'green',
        });
      } else {
        await labService.startLab(labId);
        notifications.show({
          title: 'Success',
          message: 'Lab started successfully',
          color: 'green',
        });
      }
      fetchLabs();
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to update lab',
        color: 'red',
      });
    }
  };

  const openDeleteModal = (labId: number) => {
    setLabToDelete(labId);
    setDeleteModalOpen(true);
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Stack gap="md">
          <Group justify="space-between">
            <Title order={2}>Labs Management</Title>
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => router.push('/admin/labs/new')}
            >
              Create New Lab
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

          {!loading && !error && labs.length === 0 && (
            <Alert icon={<IconAlertCircle size={16} />} color="blue" title="No Labs">
              No labs found. Create your first lab to get started.
            </Alert>
          )}

          {!loading && !error && labs.length > 0 && (
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Title</Table.Th>
                  <Table.Th>Description</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Created</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {labs.map((lab) => (
                  <Table.Tr key={lab.id}>
                    <Table.Td>
                      <Text fw={500}>{lab.title}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={2}>
                        {lab.description}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Badge color={lab.is_published ? 'green' : 'gray'}>
                          {lab.is_published ? 'Published' : 'Unpublished'}
                        </Badge>
                        {lab.is_published && (
                          <Badge color={lab.is_running ? 'blue' : 'yellow'}>
                            {lab.is_running ? 'Running' : 'Stopped'}
                          </Badge>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">
                        {new Date(lab.created_at).toLocaleDateString()}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Tooltip label={lab.is_published ? 'Unpublish' : 'Publish'}>
                          <ActionIcon
                            color={lab.is_published ? 'gray' : 'green'}
                            variant="light"
                            onClick={() => handlePublish(lab.id, lab.is_published)}
                          >
                            {lab.is_published ? <IconEyeOff size={16} /> : <IconEye size={16} />}
                          </ActionIcon>
                        </Tooltip>
                        {lab.is_published && (
                          <Tooltip label={lab.is_running ? 'Stop Lab' : 'Start Lab'}>
                            <ActionIcon
                              color={lab.is_running ? 'red' : 'blue'}
                              variant="light"
                              onClick={() => handleStartStop(lab.id, lab.is_running)}
                            >
                              {lab.is_running ? <IconPlayerStop size={16} /> : <IconPlayerPlay size={16} />}
                            </ActionIcon>
                          </Tooltip>
                        )}
                        <Tooltip label="Edit">
                          <ActionIcon
                            color="blue"
                            variant="light"
                            onClick={() => router.push(`/admin/labs/${lab.id}`)}
                            disabled={lab.is_running}
                          >
                            <IconEdit size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip label="Delete">
                          <ActionIcon
                            color="red"
                            variant="light"
                            onClick={() => openDeleteModal(lab.id)}
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
          title="Delete Lab"
        >
          <Stack>
            <Text>Are you sure you want to delete this lab? This action cannot be undone.</Text>
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
