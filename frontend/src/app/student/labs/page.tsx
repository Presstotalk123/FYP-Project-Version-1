'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Title,
  Stack,
  Card,
  Text,
  Badge,
  Button,
  Group,
  Loader,
  Alert,
  SimpleGrid,
} from '@mantine/core';
import { IconAlertCircle, IconPlayerPlay, IconEye } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { Lab } from '@/types/lab.types';
import { labService } from '@/services/lab.service';

export default function StudentLabsPage() {
  const router = useRouter();

  const [labs, setLabs] = useState<Lab[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLabs();
  }, []);

  const fetchLabs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await labService.getLabs();
      setLabs(data);
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to load labs');
    } finally {
      setLoading(false);
    }
  };

  const handleLabAction = (lab: Lab) => {
    if (lab.is_running) {
      // Start lab session
      router.push(`/student/labs/${lab.id}/workspace`);
    } else {
      // Preview mode
      router.push(`/student/labs/${lab.id}/preview`);
    }
  };

  return (
    <ProtectedRoute requiredRole={UserRole.STUDENT}>
      <DashboardLayout>
        <Stack gap="md">
          <Title order={2}>Database Labs</Title>

          {loading && (
            <Group justify="center" py="xl">
              <Loader size="lg" />
            </Group>
          )}

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {error}
            </Alert>
          )}

          {!loading && !error && labs.length === 0 && (
            <Alert icon={<IconAlertCircle size={16} />} color="blue" title="No Labs Available">
              No labs are currently published. Check back later!
            </Alert>
          )}

          {!loading && !error && labs.length > 0 && (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
              {labs.map((lab) => (
                <Card key={lab.id} shadow="sm" padding="lg" radius="md" withBorder>
                  <Stack gap="md">
                    <div>
                      <Group justify="space-between" mb="xs">
                        <Text fw={600} size="lg">
                          {lab.title}
                        </Text>
                        <Badge color={lab.is_running ? 'green' : 'yellow'} size="sm">
                          {lab.is_running ? 'Available' : 'Preview Only'}
                        </Badge>
                      </Group>
                      <Text size="sm" c="dimmed" lineClamp={3}>
                        {lab.description}
                      </Text>
                    </div>

                    <Button
                      fullWidth
                      leftSection={lab.is_running ? <IconPlayerPlay size={16} /> : <IconEye size={16} />}
                      color={lab.is_running ? 'blue' : 'gray'}
                      onClick={() => handleLabAction(lab)}
                    >
                      {lab.is_running ? 'Start Lab' : 'Preview Schema'}
                    </Button>

                    <Text size="xs" c="dimmed">
                      Created {new Date(lab.created_at).toLocaleDateString()}
                    </Text>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
