'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Title,
  Text,
  Stack,
  Group,
  Table,
  Badge,
  Loader,
  Alert,
  Card,
  ActionIcon,
  Button,
} from '@mantine/core';
import { IconAlertCircle, IconChevronLeft, IconChevronRight, IconClock } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { PlatformUsageTable } from '@/components/common/PlatformUsageTable';
import { UserRole } from '@/types/user.types';
import { loginActivityService } from '@/services/loginActivity.service';
import { queryKeys } from '@/services/query-keys';
import { formatDuration } from '@/utils/format-duration';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export default function StudentUsagePage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1); // 1-12
  const [selected, setSelected] = useState<{ id: number; name: string } | null>(null);

  const goPrev = () => {
    setSelected(null);
    if (month === 1) { setYear((y) => y - 1); setMonth(12); } else { setMonth((m) => m - 1); }
  };
  const goNext = () => {
    setSelected(null);
    if (month === 12) { setYear((y) => y + 1); setMonth(1); } else { setMonth((m) => m + 1); }
  };

  const overviewQuery = useQuery({
    queryKey: queryKeys.usageOverview(year, month),
    queryFn: () => loginActivityService.getUsageOverview(year, month),
    placeholderData: (prev) => prev,
  });

  const detailQuery = useQuery({
    queryKey: selected ? queryKeys.studentUsageByStaff(selected.id, year, month) : ['studentUsageByStaff', 'none'],
    queryFn: () => loginActivityService.getStudentUsage(selected!.id, year, month),
    enabled: selected !== null,
  });

  const rows = overviewQuery.data ?? [];

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="lg">
          <Group justify="space-between" align="flex-end">
            <div>
              <Title order={2}>Student Usage</Title>
              <Text c="dimmed" size="sm">
                Time each student spent on the platform, per calendar day. A day&apos;s time is the
                sum of that day&apos;s login sessions.
              </Text>
            </div>
            <Group gap="xs">
              <ActionIcon variant="default" onClick={goPrev} aria-label="Previous month" size="lg">
                <IconChevronLeft size={18} />
              </ActionIcon>
              <Text fw={700} w={140} ta="center">{MONTH_NAMES[month - 1]} {year}</Text>
              <ActionIcon variant="default" onClick={goNext} aria-label="Next month" size="lg">
                <IconChevronRight size={18} />
              </ActionIcon>
            </Group>
          </Group>

          {overviewQuery.isLoading ? (
            <Group justify="center" py="xl"><Loader /></Group>
          ) : overviewQuery.error ? (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Failed to load usage">
              {(overviewQuery.error as { response?: { data?: { detail?: string } } }).response?.data?.detail
                ?? 'Could not load student usage.'}
            </Alert>
          ) : rows.length === 0 ? (
            <Text c="dimmed" ta="center" py="xl">No student activity recorded this month.</Text>
          ) : (
            <Card withBorder padding="0" style={{ opacity: overviewQuery.isFetching ? 0.6 : 1 }}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Student</Table.Th>
                    <Table.Th>Class group</Table.Th>
                    <Table.Th ta="center">Active days</Table.Th>
                    <Table.Th ta="right">Total time</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((r) => (
                    <Table.Tr key={r.student_id}>
                      <Table.Td>
                        <Text fw={600} size="sm">{r.name || r.email}</Text>
                        {r.name && <Text size="xs" c="dimmed">{r.email}</Text>}
                      </Table.Td>
                      <Table.Td>{r.class_group || <Text c="dimmed" size="sm">—</Text>}</Table.Td>
                      <Table.Td ta="center">
                        <Badge variant="light">{r.active_days}</Badge>
                      </Table.Td>
                      <Table.Td ta="right">
                        <Text fw={700} size="sm">{formatDuration(r.total_seconds)}</Text>
                      </Table.Td>
                      <Table.Td ta="right">
                        <Button
                          size="compact-sm"
                          variant={selected?.id === r.student_id ? 'filled' : 'light'}
                          leftSection={<IconClock size={14} />}
                          onClick={() =>
                            setSelected(
                              selected?.id === r.student_id
                                ? null
                                : { id: r.student_id, name: r.name || r.email },
                            )
                          }
                        >
                          {selected?.id === r.student_id ? 'Hide' : 'Daily'}
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Card>
          )}

          {selected && (
            <Card withBorder padding="md">
              <Text fw={700} mb="sm">{selected.name} — daily breakdown</Text>
              {detailQuery.isLoading ? (
                <Group justify="center" py="md"><Loader size="sm" /></Group>
              ) : (
                <PlatformUsageTable
                  days={detailQuery.data?.days ?? []}
                  totalSeconds={detailQuery.data?.total_seconds ?? 0}
                  loading={detailQuery.isFetching}
                />
              )}
            </Card>
          )}
        </Stack>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
