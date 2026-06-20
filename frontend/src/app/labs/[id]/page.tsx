'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Anchor,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconArrowLeft, IconPlus, IconUsers } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { UserRole } from '@/types/user.types';
import { unifiedLabService } from '@/services/unifiedLab.service';
import { AddFromPoolModal } from '@/components/lab/AddFromPoolModal';
import { LabItemList } from '@/components/lab/LabItemList';
import type { LabItem, LabItemKind, UnifiedLabDetail } from '@/types/unified-lab.types';

function ManageLabView({ labId }: { labId: number }) {
  const router = useRouter();
  const [lab, setLab] = useState<UnifiedLabDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [poolOpen, setPoolOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setLab(await unifiedLabService.get(labId));
    } catch (err) {
      const e = err as { message?: string };
      notifications.show({ color: 'red', message: e.message || 'Failed to load lab' });
    }
  }, [labId]);

  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const addFromPool = async (picks: { kind: LabItemKind; ref_id: number }[]) => {
    for (const p of picks) {
      await unifiedLabService.addItem(labId, p.kind, p.ref_id);
    }
    await refresh();
  };

  const removeItem = async (itemId: number) => {
    await unifiedLabService.removeItem(labId, itemId);
    await refresh();
  };

  const moveItem = async (itemId: number, dir: -1 | 1) => {
    if (!lab) return;
    const items = lab.items;
    const idx = items.findIndex((i: LabItem) => i.id === itemId);
    const swap = idx + dir;
    if (swap < 0 || swap >= items.length) return;
    const ids = items.map((i: LabItem) => i.id);
    [ids[idx], ids[swap]] = [ids[swap], ids[idx]];
    await unifiedLabService.reorder(labId, ids);
    await refresh();
  };

  const onPublishToggle = async () => {
    if (!lab) return;
    setBusy(true);
    try {
      if (lab.is_published) await unifiedLabService.unpublish(labId);
      else await unifiedLabService.publish(labId);
      await refresh();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: 'red', message: e.response?.data?.detail || e.message || 'Failed' });
    } finally {
      setBusy(false);
    }
  };

  const onRunToggle = async () => {
    if (!lab) return;
    setBusy(true);
    try {
      if (lab.is_running) await unifiedLabService.stop(labId);
      else await unifiedLabService.start(labId);
      await refresh();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      notifications.show({ color: 'red', message: e.response?.data?.detail || e.message || 'Failed' });
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );
  }
  if (!lab) return null;

  const isEditable = !lab.is_running;
  const existingRefs = new Set(
    lab.items.filter((i: LabItem) => i.ref_id != null).map((i: LabItem) => `${i.kind}-${i.ref_id}`)
  );

  return (
    <Box p="xl" maw={900} mx="auto">
      {/* Back link */}
      <Anchor onClick={() => router.push('/labs')} c="dimmed" size="sm" mb="sm" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
        <IconArrowLeft size={14} /> All labs
      </Anchor>

      {/* Header */}
      <Group justify="space-between" mb="xs" mt="sm">
        <Title order={2}>{lab.title}</Title>
        <Group gap={8}>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconUsers size={14} />}
            onClick={() => router.push(`/labs/${labId}/students`)}
          >
            Students
          </Button>
          <Button
            size="xs"
            variant="light"
            onClick={() => router.push(`/labs/${labId}/workspace`)}
          >
            Open workspace
          </Button>
        </Group>
      </Group>

      {lab.description && (
        <Text c="dimmed" size="sm" mb="md">{lab.description}</Text>
      )}

      {/* Status badges + controls */}
      <Group gap={8} mb="md">
        <Badge color={lab.is_published ? 'green' : 'gray'}>
          {lab.is_published ? 'Published' : 'Unpublished'}
        </Badge>
        <Badge color={lab.is_running ? 'blue' : 'gray'}>
          {lab.is_running ? 'Running' : 'Stopped'}
        </Badge>
        <Button size="xs" variant="default" onClick={onPublishToggle} loading={busy}>
          {lab.is_published ? 'Unpublish' : 'Publish'}
        </Button>
        <Button
          size="xs"
          variant="default"
          onClick={onRunToggle}
          loading={busy}
          disabled={!lab.is_published}
        >
          {lab.is_running ? 'Stop' : 'Start'}
        </Button>
      </Group>

      <Divider mb="md" />

      {/* Content management (only when not running) */}
      <Stack gap="sm">
        <Group justify="space-between">
          <Text fw={500}>Contents ({lab.items.length} item{lab.items.length !== 1 ? 's' : ''})</Text>
          {isEditable && (
            <Group gap={8}>
              <Button
                size="xs"
                variant="light"
                leftSection={<IconPlus size={14} />}
                onClick={() => setPoolOpen(true)}
              >
                Add from pool
              </Button>
            </Group>
          )}
        </Group>

        {isEditable ? (
          <LabItemList items={lab.items} onRemove={removeItem} onMove={moveItem} />
        ) : (
          /* Read-only list when running */
          lab.items.length === 0 ? (
            <Text c="dimmed" ta="center" py="md">No items.</Text>
          ) : (
            <Stack gap={8}>
              {lab.items.map((it: LabItem, i: number) => (
                <Group key={it.id} gap="sm" px="sm" py={8} style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8 }}>
                  <Text c="dimmed" size="sm" w={20}>{i + 1}</Text>
                  <Text style={{ flex: 1 }} size="sm">
                    {it.title}
                  </Text>
                  {it.difficulty && <Badge variant="light" size="sm">{it.difficulty}</Badge>}
                  <Badge variant="light" size="sm" color={it.kind === 'sql' ? 'blue' : it.kind === 'erd' ? 'grape' : 'teal'}>
                    {it.kind.toUpperCase()}
                  </Badge>
                </Group>
              ))}
            </Stack>
          )
        )}

        {!isEditable && (
          <Text size="xs" c="dimmed" ta="center">Stop the lab to edit its contents.</Text>
        )}
      </Stack>

      <AddFromPoolModal
        opened={poolOpen}
        onClose={() => setPoolOpen(false)}
        existingRefs={existingRefs}
        onAdd={addFromPool}
      />
    </Box>
  );
}

export default function LabManagePage() {
  const params = useParams<{ id: string }>();
  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <ManageLabView labId={Number(params.id)} />
    </ProtectedRoute>
  );
}
