'use client';

import { useRouter } from 'next/navigation';
import { Box, Card, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconDatabase, IconSitemap } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';

export default function LabsHubPage() {
  const router = useRouter();
  const { isStaff } = useAuth();

  const sqlLabsHref = isStaff ? '/admin/labs' : '/student/labs';

  return (
    <ProtectedRoute>
      <Box p="xl" maw={900} mx="auto">
        <Title order={2}>Labs</Title>
        <Text c="dimmed" mb="lg">
          Collaborative, class-session labs.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <Card
            withBorder
            radius="lg"
            p="lg"
            style={{ cursor: 'pointer' }}
            onClick={() => router.push(sqlLabsHref)}
          >
            <Stack gap="sm">
              <ThemeIcon variant="light" size="lg" radius="md" color="blue">
                <IconDatabase size={22} />
              </ThemeIcon>
              <Text fw={600}>SQL Labs</Text>
              <Text size="sm" c="dimmed">
                Multi-task SQL labs with live sessions.
              </Text>
            </Stack>
          </Card>
          <Card
            withBorder
            radius="lg"
            p="lg"
            style={{ cursor: 'pointer' }}
            onClick={() => router.push('/er-diagram/labs')}
          >
            <Stack gap="sm">
              <ThemeIcon variant="light" size="lg" radius="md" color="grape">
                <IconSitemap size={22} />
              </ThemeIcon>
              <Text fw={600}>ER Labs</Text>
              <Text size="sm" c="dimmed">
                Collaborative ER diagram labs.
              </Text>
            </Stack>
          </Card>
        </SimpleGrid>
      </Box>
    </ProtectedRoute>
  );
}
