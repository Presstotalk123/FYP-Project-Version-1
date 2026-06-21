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
import { unifiedLabService } from '@/services/unifiedLab.service';
import type { UnifiedLabListItem } from '@/types/unified-lab.types';

export default function LabsPage() {
  const router = useRouter();
  const { isStaff } = useAuth();
  const [labs, setLabs] = useState<UnifiedLabListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      setLoading(true);
      setLabs(await unifiedLabService.list());
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({
        color: 'red',
        message: e.response?.data?.detail || e.message || 'Failed to load labs',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const onPublishToggle = async (lab: UnifiedLabListItem) => {
    try {
      if (lab.is_published) await unifiedLabService.unpublish(lab.id);
      else await unifiedLabService.publish(lab.id);
      refresh();
    } catch (err) {
      const e = err as { message?: string };
      notifications.show({ color: 'red', message: e.message || 'Failed' });
    }
  };

  const onRunToggle = async (lab: UnifiedLabListItem) => {
    try {
      if (lab.is_running) await unifiedLabService.stop(lab.id);
      else await unifiedLabService.start(lab.id);
      refresh();
    } catch (err) {
      const e = err as { message?: string };
      notifications.show({ color: 'red', message: e.message || 'Failed' });
    }
  };

  // Only published labs are shown to students
  const visibleLabs = isStaff ? labs : labs.filter((l) => l.is_published);

  return (
    <ProtectedRoute>
      <Box p="xl" maw={1000} mx="auto">
        <Group justify="space-between" mb="lg">
          <Title order={2}>Labs</Title>
          {isStaff && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => router.push('/labs/new')}>
              Create lab
            </Button>
          )}
        </Group>

        {loading ? (
          <Group justify="center" py="xl">
            <Loader />
          </Group>
        ) : visibleLabs.length === 0 ? (
          <Text c="dimmed">
            {isStaff ? 'No labs yet. Click "Create lab" to get started.' : 'No labs available right now.'}
          </Text>
        ) : isStaff ? (
          <Table withTableBorder striped highlightOnHover>
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
                    <Anchor onClick={() => router.push(`/labs/${lab.id}`)} style={{ cursor: 'pointer' }}>
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
                        <Menu.Item onClick={() => router.push(`/labs/${lab.id}`)}>
                          Manage
                        </Menu.Item>
                        <Menu.Item onClick={() => router.push(`/labs/${lab.id}/students`)}>
                          View students
                        </Menu.Item>
                        <Menu.Item onClick={() => onPublishToggle(lab)}>
                          {lab.is_published ? 'Unpublish' : 'Publish'}
                        </Menu.Item>
                        <Menu.Item onClick={() => onRunToggle(lab)} disabled={!lab.is_published}>
                          {lab.is_running ? 'Stop' : 'Start'}
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Table withTableBorder striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Title</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {visibleLabs.map((lab) => (
                <Table.Tr key={lab.id}>
                  <Table.Td>{lab.title}</Table.Td>
                  <Table.Td>
                    <Badge color={lab.is_running ? 'blue' : 'gray'}>
                      {lab.is_running ? 'Running' : 'Closed'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {lab.is_running ? (
                      <Button size="xs" onClick={() => router.push(`/labs/${lab.id}/join`)}>
                        Join
                      </Button>
                    ) : (
                      <Button size="xs" variant="default" disabled>
                        Not running
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
