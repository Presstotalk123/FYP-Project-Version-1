'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ActionIcon, Button, Stack, TextInput, Textarea, Title, PasswordInput, Group, Code } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { erLabsService } from '@/services/erLabs.service';

function randomPassword(): string {
  const chars = 'abcdefghjkmnpqrstuvwxyz23456789';
  return Array.from({ length: 6 }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
}

export default function NewErLabPage() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [password, setPassword] = useState(randomPassword());
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async () => {
    setSubmitting(true);
    try {
      const lab = await erLabsService.create({ title, description, join_password: password });
      notifications.show({
        color: 'green',
        title: 'Lab created',
        message: `Join code: ${lab.join_password}`,
        autoClose: 10000,
      });
      router.push(`/er-diagram/lab/${lab.id}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed';
      notifications.show({ color: 'red', message: msg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Stack p="md" maw={720}>
      <Group align="center" gap="sm">
        <ActionIcon
          component="a"
          href="/er-diagram"
          variant="subtle"
          size="sm"
          aria-label="Back to ER diagram"
        >
          <IconArrowLeft size={18} />
        </ActionIcon>
        <Title order={2}>New ER Lab</Title>
      </Group>
      <TextInput label="Title" value={title} onChange={e => setTitle(e.target.value)} required />
      <Textarea label="Description" value={description} onChange={e => setDescription(e.target.value)}
                required minRows={4} />
      <PasswordInput label="Join password (students enter this on session start)"
                     description={<>Generated: <Code>{password}</Code> — regenerate or type your own</>}
                     value={password} onChange={e => setPassword(e.target.value)} required
                     visible />
      <Group>
        <Button onClick={() => setPassword(randomPassword())} variant="default">Regenerate</Button>
        <Button onClick={onSubmit} loading={submitting}
                disabled={!title || !description || password.length < 4}>
          Create
        </Button>
      </Group>
    </Stack>
  );
}
