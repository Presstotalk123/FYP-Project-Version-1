'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Title,
  Text,
  Stack,
  Group,
  Card,
  Button,
  SimpleGrid,
  Loader,
} from '@mantine/core';
import { IconBook, IconUsers, IconChecks, IconArrowRight } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { questionService } from '@/services/question.service';
import api from '@/services/api.service';

interface Stats {
  totalQuestions: number;
  totalStudents: number;
  totalAttempts: number;
}

export default function AdminDashboard() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats>({ totalQuestions: 0, totalStudents: 0, totalAttempts: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        const questions = await questionService.getQuestions();

        // Get user count (students)
        let studentCount = 0;
        try {
          const usersResponse = await api.get('/users');
          studentCount = usersResponse.data.filter((u: any) => u.role === 'student').length;
        } catch {
          // Endpoint might not exist yet
          studentCount = 0;
        }

        // Get total attempts
        let attemptCount = 0;
        try {
          const attemptsResponse = await api.get('/attempts');
          attemptCount = attemptsResponse.data.length;
        } catch {
          attemptCount = 0;
        }

        setStats({
          totalQuestions: questions.length,
          totalStudents: studentCount,
          totalAttempts: attemptCount,
        });
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Stack gap="lg">
          <div>
            <Title order={2}>Admin Dashboard</Title>
            <Text mt="sm" c="dimmed">
              Welcome to the SQL Learning Platform administration panel
            </Text>
          </div>

          {loading ? (
            <Stack align="center" justify="center" style={{ minHeight: '200px' }}>
              <Loader size="lg" />
            </Stack>
          ) : (
            <>
              {/* Statistics Cards */}
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
                <Card withBorder padding="lg" radius="md">
                  <Group justify="space-between">
                    <div>
                      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                        Total Questions
                      </Text>
                      <Text size="xl" fw={700} mt="xs">
                        {stats.totalQuestions}
                      </Text>
                    </div>
                    <IconBook size={40} stroke={1.5} style={{ color: 'var(--mantine-color-blue-6)' }} />
                  </Group>
                </Card>

                <Card withBorder padding="lg" radius="md">
                  <Group justify="space-between">
                    <div>
                      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                        Registered Students
                      </Text>
                      <Text size="xl" fw={700} mt="xs">
                        {stats.totalStudents}
                      </Text>
                    </div>
                    <IconUsers size={40} stroke={1.5} style={{ color: 'var(--mantine-color-green-6)' }} />
                  </Group>
                </Card>

                <Card withBorder padding="lg" radius="md">
                  <Group justify="space-between">
                    <div>
                      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                        Total Attempts
                      </Text>
                      <Text size="xl" fw={700} mt="xs">
                        {stats.totalAttempts}
                      </Text>
                    </div>
                    <IconChecks size={40} stroke={1.5} style={{ color: 'var(--mantine-color-orange-6)' }} />
                  </Group>
                </Card>
              </SimpleGrid>

              {/* Quick Actions */}
              <Card withBorder padding="lg" radius="md">
                <Stack gap="md">
                  <Title order={3}>Quick Actions</Title>
                  <Group>
                    <Button
                      rightSection={<IconArrowRight size={16} />}
                      onClick={() => router.push('/admin/questions')}
                    >
                      Manage Questions
                    </Button>
                    <Button
                      variant="light"
                      rightSection={<IconArrowRight size={16} />}
                      onClick={() => router.push('/admin/questions/new')}
                    >
                      Create New Question
                    </Button>
                  </Group>
                </Stack>
              </Card>
            </>
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
