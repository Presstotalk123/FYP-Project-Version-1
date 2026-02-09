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
  Select,
} from '@mantine/core';
import { IconUser, IconLock, IconAlertCircle } from '@tabler/icons-react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { UserRole } from '@/types/user.types';

export default function RegisterForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState<UserRole>(UserRole.STUDENT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { register } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);

    try {
      await register({ email, password, role });
      const redirectPath = role === UserRole.STAFF ? '/admin' : '/student';
      router.push(redirectPath);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(
        axiosErr.response?.data?.detail ||
          'Registration failed. Please try again.'
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
            Register
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

            <PasswordInput
              leftSection={<IconLock size={16} />}
              placeholder="Confirm Password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.currentTarget.value)}
            />

            <Select
              label="Role"
              data={[
                { value: UserRole.STUDENT, label: 'Student' },
                { value: UserRole.STAFF, label: 'Staff' },
              ]}
              value={role}
              onChange={(value) => setRole(value as UserRole)}
              allowDeselect={false}
            />

            <Button type="submit" loading={loading} fullWidth>
              Register
            </Button>
          </Stack>
        </form>

        <Text size="sm" ta="center" mt="md">
          Already have an account?{' '}
          <Text component={Link} href="/login" c="blue">
            Log in
          </Text>
        </Text>
      </Card>
    </Center>
  );
}
