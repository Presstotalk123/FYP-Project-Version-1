'use client';

import { ActionIcon, Badge, Group, Paper, Stack, Text } from '@mantine/core';
import { IconArrowDown, IconArrowUp, IconX } from '@tabler/icons-react';
import { LabItem } from '@/types/unified-lab.types';

const KIND_BADGE: Record<string, { label: string; color: string }> = {
  sql: { label: 'SQL', color: 'blue' }, erd: { label: 'ERD', color: 'grape' },
  sqllab: { label: 'SQL Lab', color: 'teal' },
};

export function LabItemList({ items, onRemove, onMove }: {
  items: LabItem[]; onRemove: (id: number) => void; onMove: (id: number, dir: -1 | 1) => void;
}) {
  if (items.length === 0) return <Text c="dimmed" ta="center" py="md">No items yet. Add questions from the pool.</Text>;
  return (
    <Stack gap={8}>
      {items.map((it, i) => (
        <Paper key={it.id} withBorder p="sm" radius="md">
          <Group gap="sm" wrap="nowrap">
            <Text c="dimmed" size="sm" w={20}>{i + 1}</Text>
            <Text style={{ flex: 1 }}>{it.title}</Text>
            {it.difficulty && <Badge variant="light">{it.difficulty}</Badge>}
            <Badge variant="light" color={KIND_BADGE[it.kind].color}>{KIND_BADGE[it.kind].label}</Badge>
            <ActionIcon variant="subtle" disabled={i === 0} onClick={() => onMove(it.id, -1)} aria-label="Up"><IconArrowUp size={16} /></ActionIcon>
            <ActionIcon variant="subtle" disabled={i === items.length - 1} onClick={() => onMove(it.id, 1)} aria-label="Down"><IconArrowDown size={16} /></ActionIcon>
            <ActionIcon variant="subtle" color="red" onClick={() => onRemove(it.id)} aria-label="Remove"><IconX size={16} /></ActionIcon>
          </Group>
        </Paper>
      ))}
    </Stack>
  );
}
