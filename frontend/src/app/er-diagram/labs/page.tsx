'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ActionIcon,
  Anchor,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Menu,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconDots, IconPlus } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';
import { erLabsService } from '@/services/erLabs.service';
import type { ErLabResponse } from '@/types/er-lab.types';

export default function ERLabsPage() {
  const router = useRouter();
  const { isStaff } = useAuth();
  const [labs, setLabs] = useState<ErLabResponse[]>([]);
  const [loading, setLoading] = useState(true);

  const refreshLabs = async () => {
    try {
      setLoading(true);
      setLabs(await erLabsService.list());
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({
        color: 'red',
        message: e.response?.data?.detail || e.message || 'Failed to load ER labs',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshLabs();
  }, []);

  const onPublishToggle = async (lab: ErLabResponse) => {
    try {
      if (lab.is_published) await erLabsService.unpublish(lab.id);
      else await erLabsService.publish(lab.id);
      refreshLabs();
    } catch (err) {
      const e = err as { message?: string };
      notifications.show({ color: 'red', message: e.message || 'Failed' });
    }
  };

  const onRunToggle = async (lab: ErLabResponse) => {
    try {
      if (lab.is_running) await erLabsService.stop(lab.id);
      else await erLabsService.start(lab.id);
      refreshLabs();
    } catch (err) {
      const e = err as { message?: string };
      notifications.show({ color: 'red', message: e.message || 'Failed' });
    }
  };

  const onDelete = async (lab: ErLabResponse) => {
    if (!window.confirm(`Delete "${lab.title}"?`)) return;
    try {
      await erLabsService.remove(lab.id);
      refreshLabs();
    } catch (err) {
      const e = err as { message?: string };
      notifications.show({ color: 'red', message: e.message || 'Failed' });
    }
  };

  return (
    <ProtectedRoute>
      <Box p="xl" maw={1000} mx="auto">
        <Group justify="space-between" mb="lg">
          <Title order={2}>ER Labs</Title>
          {isStaff && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => router.push('/er-diagram/lab/new')}>
              New ER Lab
            </Button>
          )}
        </Group>

        {loading ? (
          <Group justify="center" py="xl">
            <Loader />
          </Group>
        ) : labs.length === 0 ? (
          <Text c="dimmed">
            {isStaff ? 'No labs yet. Click "New ER Lab" to create one.' : 'No labs available right now.'}
          </Text>
        ) : isStaff ? (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Title</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Updated</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {labs.map((lab) => (
                <Table.Tr key={lab.id}>
                  <Table.Td>
                    <Anchor onClick={() => router.push(`/er-diagram/lab/${lab.id}`)} style={{ cursor: 'pointer' }}>
                      {lab.title}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Badge color={lab.is_published ? 'green' : 'gray'}>
                        {lab.is_published ? 'Published' : 'Unpublished'}
                      </Badge>
                      <Badge color={lab.is_running ? 'blue' : 'gray'}>
                        {lab.is_running ? 'Running' : 'Stopped'}
                      </Badge>
                    </Group>
                  </Table.Td>
                  <Table.Td>{new Date(lab.updated_at).toLocaleString()}</Table.Td>
                  <Table.Td>
                    <Menu>
                      <Menu.Target>
                        <ActionIcon variant="subtle">
                          <IconDots />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item onClick={() => router.push(`/er-diagram/lab/${lab.id}`)}>
                          Manage questions
                        </Menu.Item>
                        <Menu.Item onClick={() => router.push(`/er-diagram/lab/${lab.id}/students`)}>
                          View students
                        </Menu.Item>
                        <Menu.Item onClick={() => onPublishToggle(lab)}>
                          {lab.is_published ? 'Unpublish' : 'Publish'}
                        </Menu.Item>
                        <Menu.Item onClick={() => onRunToggle(lab)} disabled={!lab.is_published}>
                          {lab.is_running ? 'Stop' : 'Start'}
                        </Menu.Item>
                        <Menu.Item color="red" onClick={() => onDelete(lab)}>
                          Delete
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Title</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {labs.map((lab) => (
                <Table.Tr key={lab.id}>
                  <Table.Td>{lab.title}</Table.Td>
                  <Table.Td>
                    <Badge color={lab.is_running ? 'blue' : 'gray'}>
                      {lab.is_running ? 'Running' : 'Closed'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {lab.is_running ? (
                      <Button size="xs" onClick={() => router.push(`/er-diagram/lab/${lab.id}/join`)}>
                        Join
                      </Button>
                    ) : (
                      <Button
                        size="xs"
                        variant="default"
                        onClick={() => router.push(`/er-diagram/lab/${lab.id}/history`)}
                      >
                        View history
                      </Button>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Box>
    </ProtectedRoute>
  );
}
