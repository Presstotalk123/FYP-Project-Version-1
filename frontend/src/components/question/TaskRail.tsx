'use client';
import { ActionIcon, Badge, Button, Group, Paper, Stack, Text } from '@mantine/core';
import { IconArrowDown, IconArrowUp, IconPlus, IconTrash } from '@tabler/icons-react';
import { AuthorTaskView } from '@/types/question-author.types';

export function TaskRail({ tasks, selectedId, onSelect, onAdd, onMove, onDelete }: {
  tasks: AuthorTaskView[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onAdd: () => void;
  onMove: (id: number, dir: -1 | 1) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text fw={600} size="sm">Tasks</Text>
        <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={onAdd}>Add</Button>
      </Group>
      {tasks.map((t, i) => (
        <Paper key={t.id} withBorder p="xs" radius="md"
               style={{ cursor: 'pointer', borderColor: t.id === selectedId ? 'var(--mantine-color-blue-5)' : undefined }}
               onClick={() => onSelect(t.id)}>
          <Group justify="space-between" wrap="nowrap">
            <Text size="sm" truncate>{i + 1}. {t.title || 'Untitled'}</Text>
            <Group gap={2} wrap="nowrap">
              <Badge size="xs" color={t.has_answer ? 'green' : 'yellow'}>{t.has_answer ? '✓' : '⚠'}</Badge>
              <ActionIcon size="sm" variant="subtle" disabled={i === 0} onClick={(e) => { e.stopPropagation(); onMove(t.id, -1); }}><IconArrowUp size={14} /></ActionIcon>
              <ActionIcon size="sm" variant="subtle" disabled={i === tasks.length - 1} onClick={(e) => { e.stopPropagation(); onMove(t.id, 1); }}><IconArrowDown size={14} /></ActionIcon>
              <ActionIcon size="sm" color="red" variant="subtle" onClick={(e) => { e.stopPropagation(); onDelete(t.id); }}><IconTrash size={14} /></ActionIcon>
            </Group>
          </Group>
        </Paper>
      ))}
      {tasks.length === 0 && <Text size="xs" c="dimmed">No tasks yet — add one.</Text>}
    </Stack>
  );
}
