'use client';

import { Badge, Box, Group, Text, UnstyledButton } from '@mantine/core';
import { IconCircle, IconCircleCheck } from '@tabler/icons-react';
import { LabItem, LabProgress } from '@/types/unified-lab.types';

const COLOR: Record<string, string> = { sql: 'blue', erd: 'grape', sqllab: 'teal' };

export function LabItemSidebar({ items, progress, activeId, onSelect }: {
  items: LabItem[]; progress: LabProgress | null; activeId: number | null; onSelect: (id: number) => void;
}) {
  const passed = new Set((progress?.items || []).filter((p) => p.is_passed).map((p) => p.lab_item_id));
  return (
    <Box w={220} style={{ flexShrink: 0, borderRight: '1px solid var(--mantine-color-gray-3)' }}>
      <Text size="xs" tt="uppercase" c="dimmed" p="sm">Lab items</Text>
      {items.map((it) => (
        <UnstyledButton key={it.id} onClick={() => onSelect(it.id)} style={{ display: 'block', width: '100%',
          background: activeId === it.id ? 'var(--mantine-color-gray-1)' : undefined }}>
          <Group gap={8} px="sm" py={8} wrap="nowrap">
            {passed.has(it.id) ? <IconCircleCheck size={16} color="var(--mantine-color-green-6)" />
              : <IconCircle size={16} color="var(--mantine-color-gray-4)" />}
            <Text size="sm" style={{ flex: 1 }} truncate>{it.title}</Text>
            <Badge size="xs" variant="light" color={COLOR[it.kind]}>{it.kind.toUpperCase()}</Badge>
          </Group>
        </UnstyledButton>
      ))}
    </Box>
  );
}
