'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Box, Button, Group, Select, Stack, Text, TextInput, Textarea, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import Editor from '@monaco-editor/react';
import { QuestionAuthorConfig } from '@/types/question-author.types';

export function QuestionMetaForm({ config, kindLabel }: { config: QuestionAuthorConfig; kindLabel: string }) {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [difficulty, setDifficulty] = useState('easy');
  const [seed, setSeed] = useState<Record<string, string>>(
    Object.fromEntries(config.seedFields.map((f) => [f.key, ''])),
  );
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!title.trim() || config.seedFields.some((f) => !seed[f.key]?.trim())) {
      notifications.show({ color: 'red', message: 'Title and all seed fields are required' });
      return;
    }
    setSaving(true);
    try {
      const { id } = await config.createDraft({ title, description, difficulty }, seed);
      router.push(config.newAuthorHref(id));
    } catch (e) {
      notifications.show({ color: 'red', message: (e as Error).message || 'Failed to create draft' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box p="xl" maw={900} mx="auto">
      <Title order={2} mb="md">New {kindLabel}</Title>
      <Stack gap="sm">
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
        <Textarea label="Description" value={description} onChange={(e) => setDescription(e.currentTarget.value)} autosize minRows={2} />
        <Select label="Difficulty" data={['easy', 'medium', 'hard']} value={difficulty}
                onChange={(v) => setDifficulty(v ?? 'easy')} allowDeselect={false} style={{ width: 200 }} />
        {config.seedFields.map((f) => (
          <Box key={f.key}>
            <Text size="sm" fw={500} mb={4}>{f.label}</Text>
            <Box style={{ border: '1px solid var(--mantine-color-gray-3)', borderRadius: 8 }}>
              <Editor height="180px" defaultLanguage={f.language} value={seed[f.key]}
                      onChange={(v) => setSeed((s) => ({ ...s, [f.key]: v ?? '' }))} />
            </Box>
          </Box>
        ))}
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => router.push(config.poolHref)}>Cancel</Button>
          <Button onClick={submit} loading={saving}>{'Create & author tasks'}</Button>
        </Group>
      </Stack>
    </Box>
  );
}
