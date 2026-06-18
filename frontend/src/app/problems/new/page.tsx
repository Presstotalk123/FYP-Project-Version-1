'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Anchor, Box, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconArrowLeft, IconDatabase, IconFlask, IconSitemap } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';

interface CreateOption {
  key: string;
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  color: string;
  allowed: boolean;
}

export default function CreateProblemPage() {
  const router = useRouter();
  const { isStaff, loading } = useAuth();

  const options: CreateOption[] = [
    {
      key: 'sql',
      title: 'SQL question',
      description: 'A schema, sample data, and a correct query. Auto-graded by running SQL.',
      href: '/admin/questions/new',
      icon: <IconDatabase size={22} />,
      color: 'blue',
      allowed: true,
    },
    {
      key: 'erd',
      title: 'ERD question',
      description: 'A problem statement with an AI-generated rubric. Graded from a diagram.',
      href: '/er-diagram/add',
      icon: <IconSitemap size={22} />,
      color: 'grape',
      allowed: true,
    },
    {
      key: 'sqllab',
      title: 'SQL lab question',
      description: 'A seed database plus a series of tasks. Students run SQL directly on the database.',
      href: '/admin/sql-lab-questions/new',
      icon: <IconDatabase size={22} />,
      color: 'teal',
      allowed: true,
    },
    {
      key: 'lab',
      title: 'Lab',
      description: 'A gated, multi-question session built from SQL, ERD, and SQL-lab pool questions.',
      href: '/labs/new',
      icon: <IconFlask size={22} />,
      color: 'teal',
      allowed: isStaff,
    },
  ];

  const available = options.filter((option) => option.allowed);

  // A user with only one option (a student → ERD) skips the picker entirely.
  // Wait for auth to resolve first: while it loads, isStaff is briefly false, so a staff
  // user would otherwise be redirected to the lone always-allowed option (ERD) before their
  // role arrives — never seeing the picker.
  useEffect(() => {
    if (!loading && available.length === 1) {
      router.replace(available[0].href);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, available.length]);

  // Wait for auth before deciding; then render nothing while a single-option redirect fires.
  if (loading) {
    return null;
  }
  if (available.length === 1) {
    return null;
  }

  return (
    <ProtectedRoute>
      <Box p="xl" maw={900} mx="auto">
        <Anchor onClick={() => router.push('/problems')} c="dimmed" size="sm">
          <Group gap={6}>
            <IconArrowLeft size={14} />
            Back to problems
          </Group>
        </Anchor>
        <Title order={2} mt="sm">
          Create a question
        </Title>
        <Text c="dimmed" mb="lg">
          Choose what you want to create.
        </Text>

        <SimpleGrid cols={{ base: 1, sm: Math.min(available.length, 3) }} spacing="md">
          {available.map((option) => (
            <Card
              key={option.key}
              withBorder
              radius="lg"
              p="lg"
              style={{ cursor: 'pointer' }}
              onClick={() => router.push(option.href)}
            >
              <Stack gap="sm">
                <ThemeIcon variant="light" size="lg" radius="md" color={option.color}>
                  {option.icon}
                </ThemeIcon>
                <Text fw={600}>{option.title}</Text>
                <Text size="sm" c="dimmed">
                  {option.description}
                </Text>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      </Box>
    </ProtectedRoute>
  );
}
