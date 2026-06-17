'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Box, Button, PasswordInput, Stack, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { unifiedLabService } from '@/services/unifiedLab.service';

export default function JoinLabPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const labId = Number(params.id);
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const join = async () => {
    setLoading(true);
    try {
      await unifiedLabService.startSession(labId, password);
      router.push(`/labs/${labId}/workspace`);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      notifications.show({ color: 'red', message: err.response?.data?.detail || 'Could not join' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ProtectedRoute>
      <Box p="xl" maw={420} mx="auto">
        <Title order={3} mb="md">Join lab</Title>
        <Stack>
          <PasswordInput label="Join password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
          <Button onClick={join} loading={loading}>Join</Button>
        </Stack>
      </Box>
    </ProtectedRoute>
  );
}
