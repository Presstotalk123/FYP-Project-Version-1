// frontend/src/components/admin/GraphQuestionForm.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ActionIcon, Box, Button, Group, Paper, Select, Stack, Text, TextInput, Textarea, Title } from '@mantine/core';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import Editor from '@monaco-editor/react';
import { graphQuestionService } from '@/services/graphQuestion.service';
import { GraphTaskInput } from '@/types/graph-question.types';
import { Difficulty } from '@/types/question.types';

const EMPTY_TASK: GraphTaskInput = { title: '', description: '', correct_query: '' };

export function GraphQuestionForm() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [difficulty, setDifficulty] = useState<string>('easy');
  const [seedCypher, setSeedCypher] = useState(`CREATE (alice:Person {name: 'Alice', age: 30})
CREATE (bob:Person {name: 'Bob', age: 25})
CREATE (alice)-[:KNOWS]->(bob);`);
  const [tasks, setTasks] = useState<GraphTaskInput[]>([{ ...EMPTY_TASK }]);
  const [saving, setSaving] = useState(false);

  const setTask = (i: number, patch: Partial<GraphTaskInput>) =>
    setTasks((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));
  const addTask = () => setTasks((prev) => [...prev, { ...EMPTY_TASK }]);
  const removeTask = (i: number) => setTasks((prev) => prev.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!title.trim() || !seedCypher.trim() || tasks.length === 0) {
      notifications.show({ color: 'red', message: 'Title, Cypher statements and at least one task are required' });
      return;
    }
    if (tasks.some((t) => !t.title.trim() || !t.correct_query.trim())) {
      notifications.show({ color: 'red', message: 'Every task needs a title and a correct query' });
      return;
    }
    setSaving(true);
    try {
      await graphQuestionService.create({
        title, description, difficulty: difficulty as Difficulty,
        seed_cypher: seedCypher, tasks,
      });
      notifications.show({ color: 'green', message: 'Graph question created' });
      router.push('/problems');
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message || 'Failed to create' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box p="xl" maw={900} mx="auto">
      <Title order={2} mb="md">New Graph question</Title>
      <Stack gap="sm">
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
        <Textarea label="Description" value={description} onChange={(e) => setDescription(e.currentTarget.value)} autosize minRows={2} />
        <Select label="Difficulty" data={['easy', 'medium', 'hard']} value={difficulty} onChange={(v) => setDifficulty(v ?? 'easy')} allowDeselect={false} style={{ width: 200 }} />
        <Text size="sm" fw={500}>Cypher Statements (CREATE / MERGE)</Text>
        <Box style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8 }}>
          <Editor height="200px" defaultLanguage="cypher" value={seedCypher} onChange={(v) => setSeedCypher(v ?? '')} />
        </Box>

        <Group justify="space-between" mt="md">
          <Title order={4}>Tasks</Title>
          <Button variant="light" leftSection={<IconPlus size={16} />} onClick={addTask}>Add task</Button>
        </Group>
        {tasks.map((t, i) => (
          <Paper key={i} withBorder p="sm" radius="md">
            <Group justify="space-between" mb={6}>
              <Text fw={500} size="sm">Task {i + 1}</Text>
              <ActionIcon color="red" variant="subtle" disabled={tasks.length === 1} onClick={() => removeTask(i)} aria-label="Remove task"><IconTrash size={16} /></ActionIcon>
            </Group>
            <Stack gap={6}>
              <TextInput placeholder="Task title" value={t.title} onChange={(e) => setTask(i, { title: e.currentTarget.value })} />
              <Textarea placeholder="Prompt shown to students" value={t.description} onChange={(e) => setTask(i, { description: e.currentTarget.value })} autosize minRows={2} />
              <Text size="xs" c="dimmed">Correct query (run on the seed graph to compute the expected answer)</Text>
              <Box style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8 }}>
                <Editor height="120px" defaultLanguage="cypher" value={t.correct_query} onChange={(v) => setTask(i, { correct_query: v ?? '' })} />
              </Box>
            </Stack>
          </Paper>
        ))}

        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => router.push('/problems')}>Cancel</Button>
          <Button onClick={submit} loading={saving}>Create</Button>
        </Group>
      </Stack>
    </Box>
  );
}
