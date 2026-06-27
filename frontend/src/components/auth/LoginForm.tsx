'use client';

import { useState } from 'react';
import { Alert, Card, Title, Text, Stack, Center } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { GoogleLogin, CredentialResponse } from '@react-oauth/google';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { UserRole } from '@/types/user.types';

export default function LoginForm() {
  const [error, setError] = useState<string | null>(null);
  const { googleLogin } = useAuth();
  const router = useRouter();

  const handleGoogleSuccess = async (credentialResponse: CredentialResponse) => {
    setError(null);
    const token = credentialResponse.credential;
    if (!token) {
      setError('No credential received from Google.');
      return;
    }

    try {
      const user = await googleLogin(token);
      const redirectPath =
        user.role === UserRole.STAFF || user.role === UserRole.ADMIN ? '/admin' : '/student';
      router.push(redirectPath);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(
        axiosErr.response?.data?.detail ??
          'Login failed. Contact your administrator to get access.'
      );
    }
  };

  return (
    <Center style={{ minHeight: 'calc(100vh - 60px)', background: '#f0f2f5' }}>
      <Card shadow="sm" padding="xl" radius="md" w={400}>
        <Stack gap="lg" align="center">
          <Stack gap="xs" style={{ textAlign: 'center' }}>
            <Title order={2}>SQL Learning Platform</Title>
            <Text c="dimmed">Sign in with your Google account to continue.</Text>
          </Stack>

          {error && (
            <Alert
              icon={<IconAlertCircle size={16} />}
              color="red"
              withCloseButton
              onClose={() => setError(null)}
              w="100%"
            >
              {error}
            </Alert>
          )}

          <GoogleLogin
            onSuccess={handleGoogleSuccess}
            onError={() => setError('Google sign-in failed. Please try again.')}
          />
        </Stack>
      </Card>
    </Center>
  );
}
