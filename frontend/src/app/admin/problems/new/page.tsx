'use client';

import { useRouter } from 'next/navigation';
import {
  Title,
  Text,
  Stack,
  SimpleGrid,
  Card,
  Group,
  ThemeIcon,
  Anchor,
} from '@mantine/core';
import {
  IconArrowLeft,
  IconDatabase,
  IconHierarchy,
  IconChartDots3,
} from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';

interface QuestionTypeCard {
  icon: React.ReactNode;
  iconColor: string;
  title: string;
  description: string;
  destination: string;
}

export default function CreateQuestionPage() {
  const router = useRouter();

  const types: QuestionTypeCard[] = [
    {
      icon: <IconDatabase size={28} />,
      iconColor: 'blue',
      title: 'SQL question',
      description:
        'A schema, sample data, and a correct query. Auto-graded by running SQL.',
      destination: '/admin/questions/new',
    },
    {
      icon: <IconHierarchy size={28} />,
      iconColor: 'violet',
      title: 'ERD question',
      description:
        'A problem statement with an AI-generated rubric. Graded from a diagram.',
      destination: '/er-diagram/add',
    },
    {
      icon: <IconDatabase size={28} />,
      iconColor: 'teal',
      title: 'SQL lab question',
      description:
        'A seed database plus a series of tasks. Students run SQL directly on the database.',
      destination: '/admin/labs/wizard',
    },
    {
      icon: <IconChartDots3 size={28} />,
      iconColor: 'orange',
      title: 'Graph question',
      description:
        'A seed graph plus a series of tasks. Students run Cypher directly on the graph.',
      destination: '/admin/labs/wizard?type=graph',
    },
  ];

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="xl" style={{ maxWidth: 720 }}>
          <div>
            <Anchor
              component="button"
              size="sm"
              c="dimmed"
              onClick={() => router.push('/admin/problems')}
              style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 16 }}
            >
              <IconArrowLeft size={14} />
              Back to problems
            </Anchor>

            <Title order={2}>Create a question</Title>
            <Text c="dimmed" size="sm" mt={4}>
              Choose what you want to create.
            </Text>
          </div>

          <SimpleGrid cols={3} spacing="md">
            {types.map((t) => (
              <Card
                key={t.title}
                withBorder
                padding="lg"
                radius="md"
                style={{ cursor: 'pointer' }}
                onClick={() => router.push(t.destination)}
                styles={{
                  root: {
                    transition: 'box-shadow 120ms ease',
                    '&:hover': {
                      boxShadow: 'var(--mantine-shadow-sm)',
                    },
                  },
                }}
              >
                <Stack gap="sm">
                  <ThemeIcon color={t.iconColor} variant="light" size={44} radius="md">
                    {t.icon}
                  </ThemeIcon>
                  <div>
                    <Text fw={600} size="sm">
                      {t.title}
                    </Text>
                    <Text size="xs" c="dimmed" mt={4}>
                      {t.description}
                    </Text>
                  </div>
                </Stack>
              </Card>
            ))}
          </SimpleGrid>
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
