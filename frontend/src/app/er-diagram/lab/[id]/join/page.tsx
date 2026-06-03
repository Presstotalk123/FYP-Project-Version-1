'use client';
import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Stack, Title, PasswordInput, Button, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { erLabsService } from '@/services/erLabs.service';
import { AxiosError } from 'axios';

export default function StudentErLabJoinPage() {
  const params = useParams();
  const router = useRouter();
  const labId = Number(params.id);
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const onJoin = async () => {
    setSubmitting(true);
    try {
      await erLabsService.startSession(labId, password);
      router.push(`/er-diagram/lab/${labId}/workspace`);
    } catch (e: unknown) {
      let msg = 'Failed to join';
      if (e instanceof AxiosError) {
        msg = e.response?.data?.detail ?? msg;
      }
      notifications.show({ color: 'red', message: msg });
      router.push('/er-diagram');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Stack p="md" maw={420}>
      <Title order={2}>Join ER Lab</Title>
      <Text c="dimmed">Enter the join password your instructor shared.</Text>
      <PasswordInput label="Join password" value={password}
                     onChange={e => setPassword(e.target.value)}
                     onKeyDown={e => e.key === 'Enter' && password && onJoin()} />
      <Button onClick={onJoin} loading={submitting} disabled={!password}>Join</Button>
    </Stack>
  );
}
