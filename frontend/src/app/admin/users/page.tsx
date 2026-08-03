'use client';

import { useState, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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
  Modal,
} from '@mantine/core';
import { IconTrash, IconEdit, IconAlertCircle, IconPlus, IconCheck, IconUser, IconUsers, IconUpload, IconRefresh } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import api from '@/services/api.service';
import { queryKeys } from '@/services/query-keys';

interface WhitelistEntry {
  id: number;
  email: string;
  role: UserRole;
  name: string | null;
  class_group: string | null;
  created_at: string;
}

interface AddForm {
  email: string;
  name: string;
  class_group: string;
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

const emptyForm = (): AddForm => ({ email: '', name: '', class_group: '' });

// Coerce an axios/FastAPI error into a displayable string. FastAPI returns 422
// validation errors with `detail` as an array of {type, loc, msg, ...} objects;
// rendering that array directly crashes React (error #31), so flatten it here.
const getErrorMessage = (err: unknown, fallback: string): string => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msg = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
      .filter(Boolean)
      .join(', ');
    return msg || fallback;
  }
  if (detail && typeof detail === 'object' && 'msg' in detail) {
    return String((detail as { msg: unknown }).msg);
  }
  return fallback;
};

export default function ManageUsersPage() {
  const queryClient = useQueryClient();
  const [addForm, setAddForm] = useState<Record<UserRole, AddForm>>({
    [UserRole.ADMIN]: emptyForm(),
    [UserRole.STAFF]: emptyForm(),
    [UserRole.STUDENT]: emptyForm(),
  });
  const [adding, setAdding] = useState<Record<UserRole, boolean>>({
    [UserRole.ADMIN]: false,
    [UserRole.STAFF]: false,
    [UserRole.STUDENT]: false,
  });
  const [deleting, setDeleting] = useState<number | null>(null);

  const [editingEntry, setEditingEntry] = useState<WhitelistEntry | null>(null);
  const [editForm, setEditForm] = useState<{ name: string; class_group: string }>({ name: '', class_group: '' });
  const [savingEdit, setSavingEdit] = useState(false);

  const [uploading, setUploading] = useState(false);
  const [importSummary, setImportSummary] = useState<{
    imported: number;
    skipped: any[];
    failed: any[];
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Session-cached (see providers.tsx): revisiting this page serves cache, no refetch.
  const whitelistQuery = useQuery({
    queryKey: queryKeys.whitelist,
    queryFn: async () => (await api.get('/whitelist')).data as WhitelistEntry[],
  });
  const entries = whitelistQuery.data ?? [];
  const loading = whitelistQuery.isLoading;
  const [errorDismissed, setErrorDismissed] = useState(false);
  const error = !errorDismissed && whitelistQuery.error ? 'Failed to load whitelist.' : null;
  const refreshing = whitelistQuery.isFetching;
  const refresh = () => {
    setErrorDismissed(false);
    whitelistQuery.refetch();
  };

  // After a mutation, mark the whitelist cache stale so it re-fetches once.
  const invalidateWhitelist = () => queryClient.invalidateQueries({ queryKey: queryKeys.whitelist });

  const setField = (role: UserRole, field: keyof AddForm, value: string) => {
    setAddForm((prev) => ({
      ...prev,
      [role]: { ...prev[role], [field]: value },
    }));
  };

  const handleAdd = async (role: UserRole) => {
    const form = addForm[role];
    const email = form.email.trim();
    if (!email) return;

    setAdding((prev) => ({ ...prev, [role]: true }));
    try {
      await api.post('/whitelist', {
        email,
        role,
        name: form.name.trim() || null,
        class_group: form.class_group.trim() || null,
      });
      notifications.show({
        title: 'Whitelist updated',
        message: `${email} can now sign in as ${role}.`,
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      setAddForm((prev) => ({ ...prev, [role]: emptyForm() }));
      invalidateWhitelist();
    } catch (err: unknown) {
      notifications.show({
        title: 'Error',
        message: getErrorMessage(err, 'Failed to add entry.'),
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
      invalidateWhitelist();
    } catch (err: unknown) {
      notifications.show({
        title: 'Error',
        message: getErrorMessage(err, 'Failed to remove entry.'),
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
    } finally {
      setDeleting(null);
    }
  };

  const handleEditOpen = (entry: WhitelistEntry) => {
    setEditingEntry(entry);
    setEditForm({
      name: entry.name || '',
      class_group: entry.class_group || '',
    });
  };

  const handleEditSave = async () => {
    if (!editingEntry) return;
    setSavingEdit(true);
    try {
      await api.put(`/whitelist/${editingEntry.id}`, {
        name: editForm.name.trim() || null,
        class_group: editForm.class_group.trim() || null,
      });
      notifications.show({
        title: 'User Updated',
        message: `${editingEntry.email} has been updated.`,
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      setEditingEntry(null);
      invalidateWhitelist();
    } catch (err: unknown) {
      notifications.show({
        title: 'Error',
        message: getErrorMessage(err, 'Failed to update entry.'),
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
    } finally {
      setSavingEdit(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.post('/whitelist/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setImportSummary(res.data);
      invalidateWhitelist();
    } catch (err: unknown) {
      notifications.show({
        title: 'Upload Failed',
        message: getErrorMessage(err, 'An error occurred during file upload.'),
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const getEntriesByRole = (role: UserRole) => entries.filter((e) => e.role === role);

  return (
    <ProtectedRoute requiredRole={UserRole.ADMIN}>
      <DashboardLayout>
        <Stack gap="lg">
          <Group justify="space-between" align="flex-start">
            <div>
              <Title order={2}>Manage Users</Title>
              <Text mt="sm" c="dimmed">
                Control who can sign in. Only emails on this whitelist can log in via Google SSO.
              </Text>
            </div>
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

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" withCloseButton onClose={() => setErrorDismissed(true)}>
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
                const form = addForm[role];
                return (
                  <Card key={role} withBorder padding="lg" radius="md">
                    <Stack gap="md">
                      <Group justify="space-between">
                        <Group>
                          <Title order={3}>{label} List</Title>
                          <Badge color={color} size="lg">
                            {roleEntries.length}
                          </Badge>
                        </Group>
                        {role === UserRole.STUDENT && (
                          <Group>
                            <input
                              type="file"
                              accept=".xls,.xlsx"
                              style={{ display: 'none' }}
                              ref={fileInputRef}
                              onChange={handleFileUpload}
                            />
                            <Button
                              leftSection={<IconUpload size={16} />}
                              variant="light"
                              color={color}
                              loading={uploading}
                              onClick={() => fileInputRef.current?.click()}
                            >
                              Upload Excel
                            </Button>
                          </Group>
                        )}
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
                              <Table.Th>Name</Table.Th>
                              <Table.Th>Class Group</Table.Th>
                              <Table.Th>Added</Table.Th>
                              <Table.Th style={{ width: 60 }}></Table.Th>
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {roleEntries.map((entry) => (
                              <Table.Tr key={entry.id}>
                                <Table.Td>{entry.email}</Table.Td>
                                <Table.Td>
                                  {entry.name ?? (
                                    <Text c="dimmed" size="sm" fs="italic">—</Text>
                                  )}
                                </Table.Td>
                                <Table.Td>
                                  {entry.class_group ?? (
                                    <Text c="dimmed" size="sm" fs="italic">—</Text>
                                  )}
                                </Table.Td>
                                <Table.Td>
                                  {new Date(entry.created_at).toLocaleDateString()}
                                </Table.Td>
                                <Table.Td>
                                  <Group gap="xs" wrap="nowrap">
                                    <ActionIcon
                                      color="blue"
                                      variant="subtle"
                                      onClick={() => handleEditOpen(entry)}
                                    >
                                      <IconEdit size={16} />
                                    </ActionIcon>
                                    <ActionIcon
                                      color="red"
                                      variant="subtle"
                                      loading={deleting === entry.id}
                                      onClick={() => handleDelete(entry)}
                                    >
                                      <IconTrash size={16} />
                                    </ActionIcon>
                                  </Group>
                                </Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      )}

                      {/* Add new entry — three inputs */}
                      <Group gap="sm" align="flex-end">
                        <TextInput
                          label="Email"
                          placeholder="user@example.com"
                          maxLength={255}
                          value={form.email}
                          onChange={(e) => setField(role, 'email', e.currentTarget.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleAdd(role)}
                          style={{ flex: 2 }}
                          type="email"
                          leftSection={<IconUser size={14} />}
                          required
                        />
                        <TextInput
                          label="Name"
                          placeholder="Full name (optional)"
                          maxLength={255}
                          value={form.name}
                          onChange={(e) => setField(role, 'name', e.currentTarget.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleAdd(role)}
                          style={{ flex: 2 }}
                        />
                        <TextInput
                          label="Class Group"
                          placeholder="e.g. CS3 (optional)"
                          maxLength={100}
                          value={form.class_group}
                          onChange={(e) => setField(role, 'class_group', e.currentTarget.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleAdd(role)}
                          style={{ flex: 1 }}
                          leftSection={<IconUsers size={14} />}
                        />
                        <Button
                          leftSection={<IconPlus size={16} />}
                          loading={adding[role]}
                          onClick={() => handleAdd(role)}
                          color={color}
                          style={{ alignSelf: 'flex-end' }}
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

        <Modal
          opened={!!editingEntry}
          onClose={() => setEditingEntry(null)}
          title="Edit User"
          centered
        >
          <Stack>
            <TextInput
              label="Email"
              value={editingEntry?.email || ''}
              disabled
            />
            <TextInput
              label="Name"
              placeholder="Full name"
              maxLength={255}
              value={editForm.name}
              onChange={(e) => {
                const value = e.currentTarget.value;
                setEditForm(prev => ({ ...prev, name: value }));
              }}
            />
            <TextInput
              label="Class Group"
              placeholder="e.g. CS3"
              maxLength={100}
              value={editForm.class_group}
              onChange={(e) => {
                const value = e.currentTarget.value;
                setEditForm(prev => ({ ...prev, class_group: value }));
              }}
            />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => setEditingEntry(null)}>
                Cancel
              </Button>
              <Button loading={savingEdit} onClick={handleEditSave}>
                Save
              </Button>
            </Group>
          </Stack>
        </Modal>

        <Modal
          opened={!!importSummary}
          onClose={() => setImportSummary(null)}
          title="Import Complete"
          centered
          size="lg"
        >
          {importSummary && (
            <Stack>
              <Alert icon={<IconCheck size={16} />} color="green">
                {importSummary.imported} students imported successfully.
              </Alert>
              {importSummary.skipped.length > 0 && (
                <Alert icon={<IconAlertCircle size={16} />} color="orange" title={`${importSummary.skipped.length} Skipped (already exists)`}>
                  <Stack gap="xs" style={{ maxHeight: 150, overflowY: 'auto' }}>
                    {importSummary.skipped.map((s, i) => (
                      <Text key={i} size="sm">• {s.email}</Text>
                    ))}
                  </Stack>
                </Alert>
              )}
              {importSummary.failed.length > 0 && (
                <Alert icon={<IconAlertCircle size={16} />} color="red" title={`${importSummary.failed.length} Failed (invalid data)`}>
                  <Stack gap="xs" style={{ maxHeight: 150, overflowY: 'auto' }}>
                    {importSummary.failed.map((f, i) => (
                      <Text key={i} size="sm">• {f.email}: {f.reason}</Text>
                    ))}
                  </Stack>
                </Alert>
              )}
              <Group justify="flex-end">
                <Button onClick={() => setImportSummary(null)}>Close</Button>
              </Group>
            </Stack>
          )}
        </Modal>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
