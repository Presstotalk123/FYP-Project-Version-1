'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Box, Button, Group, Stack, TextInput, Textarea, Title, Text, ActionIcon, Divider } from '@mantine/core';
import { IconPlus, IconRefresh, IconDatabase } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import Editor from '@monaco-editor/react';
import { unifiedLabService } from '@/services/unifiedLab.service';
import { LabItem } from '@/types/unified-lab.types';
import { AddFromPoolModal } from './AddFromPoolModal';
import { LabItemList } from './LabItemList';

function randomPassword(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let s = '';
  for (let i = 0; i < 6; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return `JOIN-${s}`;
}

export function LabBuilder() {
  const router = useRouter();
  const [labId, setLabId] = useState<number | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [password, setPassword] = useState(randomPassword());
  const [withSection, setWithSection] = useState(false);
  const [schemaSql, setSchemaSql] = useState('CREATE TABLE ...;');
  const [sampleSql, setSampleSql] = useState('INSERT INTO ...;');
  const [items, setItems] = useState<LabItem[]>([]);
  const [poolOpen, setPoolOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const ensureLab = async (): Promise<number> => {
    if (labId) return labId;
    const res = await unifiedLabService.create({
      title: title || 'Untitled lab', description: description || ' ', join_password: password,
      schema_sql: withSection ? schemaSql : null, sample_data_sql: withSection ? sampleSql : null,
    });
    setLabId(res.id);
    return res.id;
  };

  const refresh = async (id: number) => setItems((await unifiedLabService.get(id)).items);

  const addFromPool = async (picks: { kind: 'sql' | 'erd'; ref_id: number }[]) => {
    try {
      const id = await ensureLab();
      for (const p of picks) await unifiedLabService.addItem(id, p.kind, p.ref_id);
      await refresh(id);
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message || 'Failed to add items' });
    }
  };

  const addSection = async () => {
    const id = await ensureLab();
    try {
      await unifiedLabService.addItem(id, 'sqllab', null);
      await refresh(id);
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message || 'Failed to add section' });
    }
  };

  const removeItem = async (itemId: number) => {
    if (!labId) return;
    await unifiedLabService.removeItem(labId, itemId);
    await refresh(labId);
  };

  const move = async (itemId: number, dir: -1 | 1) => {
    const idx = items.findIndex((i) => i.id === itemId);
    const swap = idx + dir;
    if (swap < 0 || swap >= items.length || !labId) return;
    const ids = items.map((i) => i.id);
    [ids[idx], ids[swap]] = [ids[swap], ids[idx]];
    await unifiedLabService.reorder(labId, ids);
    await refresh(labId);
  };

  const publish = async () => {
    setSaving(true);
    try {
      const id = await ensureLab();
      await unifiedLabService.publish(id);
      await unifiedLabService.start(id);
      router.push('/labs');
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message || 'Publish failed' });
    } finally {
      setSaving(false);
    }
  };

  const existingRefs = new Set(items.filter((i) => i.ref_id != null).map((i) => `${i.kind}-${i.ref_id}`));

  return (
    <Box p="xl" maw={900} mx="auto">
      <Title order={2} mb="md">Create lab</Title>
      <Stack gap="sm">
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
        <Textarea label="Description" value={description} onChange={(e) => setDescription(e.currentTarget.value)} autosize minRows={2} />
        <Group align="flex-end">
          <TextInput label="Join password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} disabled={labId !== null} style={{ width: 220 }} />
          <ActionIcon variant="subtle" disabled={labId !== null} onClick={() => setPassword(randomPassword())} aria-label="Regenerate"><IconRefresh size={18} /></ActionIcon>
          <Text size="xs" c="dimmed">Students enter this to join.{labId ? ' (locked after first save)' : ''}</Text>
        </Group>

        <Divider my="sm" label="Shared-DB section (optional)" />
        {!withSection ? (
          <Button variant="light" leftSection={<IconDatabase size={16} />} onClick={() => setWithSection(true)} disabled={labId !== null}>
            Add a shared-DB section
          </Button>
        ) : (
          <Stack gap={6}>
            <Text size="sm" fw={500}>Schema SQL</Text>
            <Editor height="120px" defaultLanguage="sql" value={schemaSql} onChange={(v) => setSchemaSql(v ?? '')} />
            <Text size="sm" fw={500}>Sample data SQL</Text>
            <Editor height="120px" defaultLanguage="sql" value={sampleSql} onChange={(v) => setSampleSql(v ?? '')} />
            <Text size="xs" c="dimmed">After saving, add the section to the contents and author its tasks on the manage page.</Text>
          </Stack>
        )}

        <Divider my="sm" label="Contents" />
        <Group justify="flex-end">
          <Button variant="light" leftSection={<IconPlus size={16} />} onClick={() => setPoolOpen(true)}>Add from pool</Button>
          <Button variant="default" leftSection={<IconDatabase size={16} />} onClick={addSection}>Add shared-DB section</Button>
        </Group>
        <LabItemList items={items} onRemove={removeItem} onMove={move} />

        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => router.push('/labs')}>Save draft</Button>
          <Button onClick={publish} loading={saving} disabled={items.length === 0}>Publish</Button>
        </Group>
      </Stack>

      <AddFromPoolModal opened={poolOpen} onClose={() => setPoolOpen(false)} existingRefs={existingRefs} onAdd={addFromPool} />
    </Box>
  );
}
