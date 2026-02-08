'use client';

import { useState } from 'react';
import {
  TextInput,
  PasswordInput,
  Button,
  Alert,
  Card,
  Title,
  Text,
  Stack,
  Center,
} from '@mantine/core';
import { IconUser, IconLock, IconAlertCircle } from '@tabler/icons-react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { UserRole } from '@/types/user.types';

export default function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const loggedInUser = await login({ email, password });
      const redirectPath =
        loggedInUser.role === UserRole.STAFF ? '/admin' : '/student';
      router.push(redirectPath);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(
        axiosErr.response?.data?.detail ||
          'Login failed. Please check your credentials.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Center style={{ minHeight: 'calc(100vh - 60px)', background: '#f0f2f5' }}>
      <Card shadow="sm" padding="xl" radius="md" w={400}>
        <Stack gap="xs" mb="lg" style={{ textAlign: 'center' }}>
          <Title order={2}>SQL Learning Platform</Title>
          <Title order={4} c="dimmed">
            Login
          </Title>
        </Stack>

        {error && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            color="red"
            mb="md"
            withCloseButton
            onClose={() => setError(null)}
          >
            {error}
          </Alert>
        )}

        <form onSubmit={handleSubmit}>
          <Stack gap="md">
            <TextInput
              leftSection={<IconUser size={16} />}
              placeholder="Email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
            />

            <PasswordInput
              leftSection={<IconLock size={16} />}
              placeholder="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
            />

            <Button type="submit" loading={loading} fullWidth>
              Log in
            </Button>
          </Stack>
        </form>

        <Text size="sm" ta="center" mt="md">
          Don&apos;t have an account?{' '}
          <Text component={Link} href="/register" c="blue">
            Register now
          </Text>
        </Text>
      </Card>
    </Center>
  );
}
