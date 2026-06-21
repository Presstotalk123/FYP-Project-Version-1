'use client';

import { useEffect, useState } from 'react';
import { Modal, Stack, Group, TextInput, Select, Checkbox, Badge, Button, Text, Loader } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconSearch } from '@tabler/icons-react';
import { problemService } from '@/services/problem.service';
import { ProblemListItem } from '@/types/problem.types';
import { LabItemKind } from '@/types/unified-lab.types';

interface AddFromPoolModalProps {
  opened: boolean;
  onClose: () => void;
  existingRefs: Set<string>;                 // `${type}-${id}` already in the lab
  onAdd: (picks: { kind: LabItemKind; ref_id: number }[]) => void;
}

export function AddFromPoolModal({ opened, onClose, existingRefs, onAdd }: AddFromPoolModalProps) {
  const [items, setItems] = useState<ProblemListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [difficulty, setDifficulty] = useState<string | null>('all');
  const [search, setSearch] = useState('');
  const [debounced] = useDebouncedValue(search, 400);
  const [picked, setPicked] = useState<Map<string, { kind: LabItemKind; ref_id: number }>>(new Map());

  useEffect(() => {
    if (!opened) return;
    setLoading(true);
    problemService
      .getProblems({
        difficulty: difficulty && difficulty !== 'all' ? (difficulty as 'easy' | 'medium' | 'hard') : undefined,
        search: debounced || undefined,
      })
      .then((r) => setItems(r.items))
      .finally(() => setLoading(false));
  }, [opened, difficulty, debounced]);

  const toggle = (it: ProblemListItem) =>
    setPicked((prev) => {
      const key = `${it.type}-${it.id}`;
      const next = new Map(prev);
      next.has(key) ? next.delete(key) : next.set(key, { kind: it.type, ref_id: it.id });
      return next;
    });

  const confirm = () => {
    onAdd(Array.from(picked.values()));
    setPicked(new Map());
    onClose();
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Add from pool" size="lg">
      <Stack gap="sm">
        <Group>
          <TextInput placeholder="Search…" leftSection={<IconSearch size={16} />} value={search}
                     onChange={(e) => setSearch(e.currentTarget.value)} style={{ flex: 1 }} />
          <Select data={[{ value: 'all', label: 'All' }, { value: 'easy', label: 'Easy' },
                         { value: 'medium', label: 'Medium' }, { value: 'hard', label: 'Hard' }]}
                  value={difficulty} onChange={setDifficulty} allowDeselect={false} style={{ width: 140 }} />
        </Group>
        {loading ? <Group justify="center" py="md"><Loader size="sm" /></Group> : (
          <Stack gap={4} mah={360} style={{ overflowY: 'auto' }}>
            {items.map((it) => {
              const key = `${it.type}-${it.id}`;
              const already = existingRefs.has(key);
              return (
                <Group key={key} gap="sm" wrap="nowrap" px="xs" py={6}
                       style={{ opacity: already ? 0.5 : 1 }}>
                  <Checkbox checked={picked.has(key)} disabled={already} onChange={() => toggle(it)} />
                  <Text style={{ flex: 1 }} size="sm">{it.title}</Text>
                  <Badge variant="light" color={it.type === 'sql' ? 'blue' : it.type === 'erd' ? 'grape' : it.type === 'graph' ? 'orange' : 'teal'}>{it.type.toUpperCase()}</Badge>
                  <Badge variant="light">{it.difficulty}</Badge>
                  {already && <Text size="xs" c="dimmed">added</Text>}
                </Group>
              );
            })}
          </Stack>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button onClick={confirm} disabled={picked.size === 0}>Add {picked.size || ''}</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
