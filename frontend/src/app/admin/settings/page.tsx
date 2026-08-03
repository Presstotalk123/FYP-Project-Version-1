'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconAlertCircle, IconRefresh } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { erdPromptsService } from '@/services/erd-prompts.service';
import { queryKeys } from '@/services/query-keys';
import type { ErdPromptListItem, ErdPromptVersionSummary } from '@/types/erd-prompts.types';
import { getApiErrorMessage } from '@/utils/api-error';

function activeContent(p: ErdPromptListItem): string {
  return p.active ? p.active.content : p.default_content;
}

export default function AdminSettingsPage() {
  const queryClient = useQueryClient();
  const [prompts, setPrompts] = useState<ErdPromptListItem[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [versions, setVersions] = useState<ErdPromptVersionSummary[]>([]);
  const [editorValue, setEditorValue] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Cache the prompt list and per-key version history for the session (see
  // providers.tsx). fetchQuery returns cached data without a network call on
  // revisits; an invalidated key (after save/restore) is refetched once.
  const loadPromptList = useCallback(
    () =>
      queryClient.fetchQuery({
        queryKey: queryKeys.erdPrompts,
        queryFn: () => erdPromptsService.list(),
        staleTime: Infinity,
      }),
    [queryClient],
  );
  const loadVersions = useCallback(
    (key: string) =>
      queryClient.fetchQuery({
        queryKey: queryKeys.erdPromptVersions(key),
        queryFn: () => erdPromptsService.versions(key),
        staleTime: Infinity,
      }),
    [queryClient],
  );
  // modals
  const [viewModal, setViewModal] = useState<{ title: string; content: string } | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState<number | 'default' | null>(null);
  const [pendingSelect, setPendingSelect] = useState<string | null>(null);

  const selected = prompts.find((p) => p.key === selectedKey) ?? null;
  const dirty = selected !== null && editorValue !== activeContent(selected);

  const refresh = useCallback(async (keepKey?: string | null) => {
    const list = await loadPromptList();
    setPrompts(list);
    const key = keepKey ?? list[0]?.key ?? null;
    setSelectedKey(key);
    const item = list.find((p) => p.key === key);
    if (item) {
      setEditorValue(activeContent(item));
      setVersions(await loadVersions(item.key));
    }
  }, [loadPromptList, loadVersions]);

  // Lighter-weight refresh used after save/activate/reset: only the affected
  // prompt's versions are re-fetched instead of the entire prompt list.
  const refreshSelected = useCallback(
    async (key: string) => {
      // A save/activate/reset changed this prompt: drop the stale cached versions
      // (and the list, whose override badges just changed) so both re-fetch fresh.
      await queryClient.invalidateQueries({ queryKey: queryKeys.erdPromptVersions(key) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.erdPrompts });
      const vs = await loadVersions(key);
      setVersions(vs);
      const active = vs.find((v) => v.is_active) ?? null;
      const current = prompts.find((p) => p.key === key);
      const defaultContent = current?.default_content ?? '';
      setPrompts((prev) =>
        prev.map((p) => (p.key === key ? { ...p, is_overridden: active !== null, active } : p)),
      );
      setEditorValue(active ? active.content : defaultContent);
    },
    [prompts, queryClient, loadVersions],
  );

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await refresh();
      } catch (err) {
        setError(getApiErrorMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [refresh]);

  const selectPrompt = (key: string) => {
    // Block switching while a save/restore is in flight: the completing
    // refresh() would snap the selection back to the old key and silently
    // discard edits started on the newly selected prompt.
    if (busy) return;
    if (key === selectedKey) return;
    if (dirty) {
      setPendingSelect(key);
      return;
    }
    void doSelect(key);
  };

  const doSelect = async (key: string) => {
    setPendingSelect(null);
    setSelectedKey(key);
    const item = prompts.find((p) => p.key === key);
    if (item) {
      setEditorValue(activeContent(item));
      try {
        setVersions(await loadVersions(key));
      } catch (err) {
        notifications.show({ color: 'red', title: 'Failed to load history', message: getApiErrorMessage(err) });
      }
    }
  };

  // Manual refresh: drop caches for the list and current prompt's versions so the
  // next load pulls fresh data from the server, keeping the current selection.
  const handleRefresh = async () => {
    if (busy || refreshing) return;
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries({ queryKey: queryKeys.erdPrompts });
      if (selectedKey) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.erdPromptVersions(selectedKey) });
      }
      await refresh(selectedKey);
    } catch (err) {
      notifications.show({ color: 'red', title: 'Refresh failed', message: getApiErrorMessage(err) });
    } finally {
      setRefreshing(false);
    }
  };

  const handleSave = async () => {
    if (!selected || !dirty || busy) return;
    setBusy(true);
    try {
      const saved = await erdPromptsService.save(selected.key, editorValue);
      notifications.show({
        color: 'green',
        title: `Saved as v${saved.version_no}`,
        message: 'The new prompt is live for the next student request.',
      });
      await refreshSelected(selected.key);
    } catch (err) {
      notifications.show({ color: 'red', title: 'Save failed', message: getApiErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleRestore = async (versionNo: number | 'default') => {
    if (!selected || busy) return;
    setBusy(true);
    try {
      if (versionNo === 'default') {
        await erdPromptsService.resetToDefault(selected.key);
        notifications.show({ color: 'green', title: 'Reset to code default', message: selected.label });
      } else {
        await erdPromptsService.activate(selected.key, versionNo);
        notifications.show({ color: 'green', title: `Restored v${versionNo}`, message: selected.label });
      }
      await refreshSelected(selected.key);
    } catch (err) {
      notifications.show({ color: 'red', title: 'Restore failed', message: getApiErrorMessage(err) });
    } finally {
      setBusy(false);
      setConfirmReset(false);
      setConfirmRestore(null);
    }
  };

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <div>
              <Title order={2}>Settings</Title>
              <Text c="dimmed" size="sm">
                Tune the AI prompts used by the LangGraph tutor. Changes go live immediately and only
                affect the LangGraph engine.
              </Text>
            </div>
            <Button
              variant="default"
              leftSection={<IconRefresh size={16} />}
              loading={refreshing}
              disabled={busy}
              onClick={handleRefresh}
              title="Reload latest data from the server"
            >
              Refresh
            </Button>
          </Group>

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Failed to load prompts">
              {error}
            </Alert>
          )}
          {loading ? (
            <Loader />
          ) : (
            <Group align="flex-start" gap="md" wrap="nowrap">
              {/* Prompt list */}
              <Card withBorder p={0} style={{ width: 280, flexShrink: 0 }}>
                {prompts.map((p) => (
                  <div
                    key={p.key}
                    role="button"
                    tabIndex={0}
                    onClick={() => selectPrompt(p.key)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        selectPrompt(p.key);
                      }
                    }}
                    style={{
                      padding: '12px 14px',
                      cursor: 'pointer',
                      borderLeft:
                        p.key === selectedKey
                          ? '3px solid var(--mantine-color-blue-6)'
                          : '3px solid transparent',
                      background: p.key === selectedKey ? 'var(--mantine-color-blue-0)' : undefined,
                      borderBottom: '1px solid var(--mantine-color-gray-2)',
                    }}
                  >
                    <Group gap="xs">
                      <Text size="sm" fw={600}>{p.label}</Text>
                      {p.is_overridden ? (
                        <Badge size="xs" color="yellow">modified · v{p.active?.version_no}</Badge>
                      ) : (
                        <Badge size="xs" color="gray">default</Badge>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed" mt={2}>{p.description}</Text>
                  </div>
                ))}
              </Card>

              {/* Editor */}
              {selected && (
                <Card withBorder style={{ flex: 1, minWidth: 0 }}>
                  <Group justify="space-between" align="flex-start" mb="sm">
                    <div>
                      <Group gap="xs">
                        <Text fw={700}>{selected.label}</Text>
                        {selected.is_overridden ? (
                          <Badge size="xs" color="yellow">modified · v{selected.active?.version_no} active</Badge>
                        ) : (
                          <Badge size="xs" color="gray">code default active</Badge>
                        )}
                      </Group>
                      <Text size="xs" c="dimmed">
                        Key: {selected.key} · affects the LangGraph engine only · live on the next request after saving
                      </Text>
                    </div>
                    <Button
                      variant="default"
                      size="xs"
                      onClick={() => setViewModal({ title: `${selected.label} — code default`, content: selected.default_content })}
                    >
                      View code default
                    </Button>
                  </Group>

                  <Textarea
                    value={editorValue}
                    onChange={(e) => setEditorValue(e.currentTarget.value)}
                    disabled={busy}
                    autosize
                    minRows={14}
                    maxRows={26}
                    styles={{ input: { fontFamily: 'ui-monospace, Consolas, monospace', fontSize: 12 } }}
                  />
                  <Text size="xs" c="dimmed" ta="right" mt={4}>
                    {editorValue.length.toLocaleString()} characters{dirty ? ' · unsaved changes' : ''}
                  </Text>

                  <Group mt="sm" gap="xs">
                    <Button onClick={handleSave} loading={busy} disabled={!dirty}>
                      Save (goes live immediately)
                    </Button>
                    <Button
                      variant="default"
                      disabled={!dirty || busy}
                      onClick={() => setEditorValue(activeContent(selected))}
                    >
                      Discard changes
                    </Button>
                    <Button
                      variant="outline"
                      color="red"
                      disabled={!selected.is_overridden || busy}
                      onClick={() => setConfirmReset(true)}
                    >
                      Reset to code default…
                    </Button>
                  </Group>

                  <Title order={5} mt="lg" mb="xs">Version history</Title>
                  <Table striped withTableBorder>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Version</Table.Th>
                        <Table.Th>Saved by</Table.Th>
                        <Table.Th>When</Table.Th>
                        <Table.Th>Status</Table.Th>
                        <Table.Th></Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {versions.map((v) => (
                        <Table.Tr key={v.version_no}>
                          <Table.Td>v{v.version_no}</Table.Td>
                          <Table.Td>{v.created_by_email ?? '—'}</Table.Td>
                          <Table.Td>{v.created_at ? new Date(v.created_at).toLocaleString() : '—'}</Table.Td>
                          <Table.Td>{v.is_active && <Badge size="xs" color="green">active</Badge>}</Table.Td>
                          <Table.Td>
                            <Group gap="xs">
                              <Button
                                size="compact-xs"
                                variant="subtle"
                                onClick={() => setViewModal({ title: `${selected.label} — v${v.version_no}`, content: v.content })}
                              >
                                View
                              </Button>
                              {!v.is_active && (
                                <Button size="compact-xs" variant="subtle" onClick={() => setConfirmRestore(v.version_no)}>
                                  Restore
                                </Button>
                              )}
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                      <Table.Tr>
                        <Table.Td><Text size="sm" c="dimmed">code default</Text></Table.Td>
                        <Table.Td><Text size="sm" c="dimmed">prompts.py</Text></Table.Td>
                        <Table.Td><Text size="sm" c="dimmed">—</Text></Table.Td>
                        <Table.Td>{!selected.is_overridden && <Badge size="xs" color="green">active</Badge>}</Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <Button
                              size="compact-xs"
                              variant="subtle"
                              onClick={() => setViewModal({ title: `${selected.label} — code default`, content: selected.default_content })}
                            >
                              View
                            </Button>
                            {selected.is_overridden && (
                              <Button size="compact-xs" variant="subtle" onClick={() => setConfirmRestore('default')}>
                                Restore
                              </Button>
                            )}
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    </Table.Tbody>
                  </Table>
                </Card>
              )}
            </Group>
          )}
        </Stack>

        {/* View content modal */}
        <Modal opened={viewModal !== null} onClose={() => setViewModal(null)} title={viewModal?.title} size="xl">
          <Textarea value={viewModal?.content ?? ''} readOnly autosize minRows={12} maxRows={28}
            styles={{ input: { fontFamily: 'ui-monospace, Consolas, monospace', fontSize: 12 } }} />
        </Modal>

        {/* Reset confirm */}
        <Modal opened={confirmReset} onClose={() => setConfirmReset(false)} title="Reset to code default?">
          <Text size="sm">
            The override will be deactivated and the code default becomes live immediately.
            Version history is kept — you can restore any version later.
          </Text>
          <Group mt="md" justify="flex-end">
            <Button variant="default" onClick={() => setConfirmReset(false)}>Cancel</Button>
            <Button color="red" loading={busy} onClick={() => void handleRestore('default')}>Reset</Button>
          </Group>
        </Modal>

        {/* Restore confirm */}
        <Modal opened={confirmRestore !== null} onClose={() => setConfirmRestore(null)}
          title={confirmRestore === 'default' ? 'Restore code default?' : `Restore v${confirmRestore}?`}>
          <Text size="sm">This version becomes live immediately for the next student request.</Text>
          <Group mt="md" justify="flex-end">
            <Button variant="default" onClick={() => setConfirmRestore(null)}>Cancel</Button>
            <Button loading={busy} onClick={() => confirmRestore !== null && void handleRestore(confirmRestore)}>
              Restore
            </Button>
          </Group>
        </Modal>

        {/* Unsaved-changes guard */}
        <Modal opened={pendingSelect !== null} onClose={() => setPendingSelect(null)} title="Discard unsaved changes?">
          <Text size="sm">You have unsaved edits to this prompt. Switching will discard them.</Text>
          <Group mt="md" justify="flex-end">
            <Button variant="default" onClick={() => setPendingSelect(null)}>Keep editing</Button>
            <Button color="red" onClick={() => pendingSelect && void doSelect(pendingSelect)}>Discard</Button>
          </Group>
        </Modal>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
