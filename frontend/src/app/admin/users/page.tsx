'use client';

import { useEffect, useState } from 'react';
import {
  Title,
  Text,
  Stack,
  Group,
  Table,
  Badge,
  ActionIcon,
  Loader,
  Alert,
  TextInput,
  Button,
  Card,
} from '@mantine/core';
import { IconTrash, IconAlertCircle, IconPlus, IconCheck } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import api from '@/services/api.service';

interface WhitelistEntry {
  id: number;
  email: string;
  role: UserRole;
  created_at: string;
}

type RoleSection = {
  role: UserRole;
  label: string;
  color: string;
};

const ROLE_SECTIONS: RoleSection[] = [
  { role: UserRole.ADMIN, label: 'Admin', color: 'red' },
  { role: UserRole.STAFF, label: 'Staff', color: 'blue' },
  { role: UserRole.STUDENT, label: 'Student', color: 'green' },
];

export default function ManageUsersPage() {
  const [entries, setEntries] = useState<WhitelistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addEmail, setAddEmail] = useState<Record<UserRole, string>>({
    [UserRole.ADMIN]: '',
    [UserRole.STAFF]: '',
    [UserRole.STUDENT]: '',
  });
  const [adding, setAdding] = useState<Record<UserRole, boolean>>({
    [UserRole.ADMIN]: false,
    [UserRole.STAFF]: false,
    [UserRole.STUDENT]: false,
  });
  const [deleting, setDeleting] = useState<number | null>(null);

  const fetchWhitelist = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get('/whitelist');
      setEntries(res.data);
    } catch {
      setError('Failed to load whitelist.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWhitelist();
  }, []);

  const handleAdd = async (role: UserRole) => {
    const email = addEmail[role].trim();
    if (!email) return;

    setAdding((prev) => ({ ...prev, [role]: true }));
    try {
      await api.post('/whitelist', { email, role });
      notifications.show({
        title: 'Whitelist updated',
        message: `${email} can now sign in as ${role}.`,
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      setAddEmail((prev) => ({ ...prev, [role]: '' }));
      fetchWhitelist();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: axiosErr.response?.data?.detail ?? 'Failed to add entry.',
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
    } finally {
      setAdding((prev) => ({ ...prev, [role]: false }));
    }
  };

  const handleDelete = async (entry: WhitelistEntry) => {
    setDeleting(entry.id);
    try {
      await api.delete(`/whitelist/${entry.id}`);
      notifications.show({
        title: 'Removed',
        message: `${entry.email} has been removed from the whitelist.`,
        color: 'orange',
        icon: <IconCheck size={16} />,
      });
      fetchWhitelist();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: axiosErr.response?.data?.detail ?? 'Failed to remove entry.',
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
    } finally {
      setDeleting(null);
    }
  };

  const getEntriesByRole = (role: UserRole) => entries.filter((e) => e.role === role);

  return (
    <ProtectedRoute requiredRole={UserRole.ADMIN}>
      <DashboardLayout>
        <Stack gap="lg">
          <div>
            <Title order={2}>Manage Users</Title>
            <Text mt="sm" c="dimmed">
              Control who can sign in. Only emails on this whitelist can log in via Google SSO.
            </Text>
          </div>

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" withCloseButton onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {loading ? (
            <Stack align="center" justify="center" style={{ minHeight: '200px' }}>
              <Loader size="lg" />
            </Stack>
          ) : (
            <Stack gap="xl">
              {ROLE_SECTIONS.map(({ role, label, color }) => {
                const roleEntries = getEntriesByRole(role);
                return (
                  <Card key={role} withBorder padding="lg" radius="md">
                    <Stack gap="md">
                      <Group>
                        <Title order={3}>{label} List</Title>
                        <Badge color={color} size="lg">
                          {roleEntries.length}
                        </Badge>
                      </Group>

                      {roleEntries.length === 0 ? (
                        <Text c="dimmed" size="sm">
                          No emails in this list.
                        </Text>
                      ) : (
                        <Table striped highlightOnHover>
                          <Table.Thead>
                            <Table.Tr>
                              <Table.Th>Email</Table.Th>
                              <Table.Th>Added</Table.Th>
                              <Table.Th style={{ width: 60 }}></Table.Th>
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {roleEntries.map((entry) => (
                              <Table.Tr key={entry.id}>
                                <Table.Td>{entry.email}</Table.Td>
                                <Table.Td>
                                  {new Date(entry.created_at).toLocaleDateString()}
                                </Table.Td>
                                <Table.Td>
                                  <ActionIcon
                                    color="red"
                                    variant="subtle"
                                    loading={deleting === entry.id}
                                    onClick={() => handleDelete(entry)}
                                  >
                                    <IconTrash size={16} />
                                  </ActionIcon>
                                </Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      )}

                      <Group gap="sm">
                        <TextInput
                          placeholder={`Add email to ${label} list`}
                          value={addEmail[role]}
                          onChange={(e) => {
                            const value = e.currentTarget.value;
                            setAddEmail((prev) => ({ ...prev, [role]: value }));
                          }}
                          onKeyDown={(e) => e.key === 'Enter' && handleAdd(role)}
                          style={{ flex: 1 }}
                          type="email"
                        />
                        <Button
                          leftSection={<IconPlus size={16} />}
                          loading={adding[role]}
                          onClick={() => handleAdd(role)}
                          color={color}
                        >
                          Add
                        </Button>
                      </Group>
                    </Stack>
                  </Card>
                );
              })}
            </Stack>
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
