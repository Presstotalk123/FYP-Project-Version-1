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
  Drawer,
  ScrollArea,
  TextInput,
} from '@mantine/core';
import { IconAlertCircle, IconChevronLeft, IconChevronRight, IconClock, IconReportAnalytics, IconSearch, IconArrowUp, IconArrowDown, IconArrowsSort } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { PlatformUsageTable } from '@/components/common/PlatformUsageTable';
import { StudentReportDrawer } from '@/components/admin/StudentReportDrawer';
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
  // Filters the table by name, email, or class group.
  const [search, setSearch] = useState('');
  // Assessment-avg sort: null = default (all-time order); 'desc' = highest→lowest; 'asc' = lowest→highest
  const [avgSort, setAvgSort] = useState<'asc' | 'desc' | null>(null);
  // Drives the per-student report drawer (practice + assessment scores).
  const [reportStudent, setReportStudent] = useState<{ id: number; name: string } | null>(null);

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

  // Gradebook colouring for the overall assessment average, matching the assessment pages.
  const scoreColor = (s: number) => (s >= 75 ? 'green' : s >= 50 ? 'yellow' : 'red');

  const rows = overviewQuery.data ?? [];
  const q = search.trim().toLowerCase();
  const filteredRows = rows.filter(
    (r) =>
      !q ||
      (r.name ?? '').toLowerCase().includes(q) ||
      r.email.toLowerCase().includes(q) ||
      (r.class_group ?? '').toLowerCase().includes(q),
  );
  // Sort by assessment average when active; students with no score always sort last.
  const sortedRows =
    avgSort === null
      ? filteredRows
      : [...filteredRows].sort((a, b) => {
          const sa = a.avg_assessment_score;
          const sb = b.avg_assessment_score;
          if (sa == null && sb == null) return 0;
          if (sa == null) return 1;
          if (sb == null) return -1;
          return avgSort === 'desc' ? sb - sa : sa - sb;
        });

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <Stack gap="lg">
          <Group justify="space-between" align="flex-end">
            <div>
              <Title order={2}>Student Usage</Title>
              <Text c="dimmed" size="sm">
                Total time each student has spent on the platform (all-time), plus the selected
                month. A day&apos;s time is the sum of that day&apos;s login sessions.
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
            <>
            <TextInput
              leftSection={<IconSearch size={16} />}
              placeholder="Search by name, email, or class group…"
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
            />
            {filteredRows.length === 0 ? (
              <Text c="dimmed" ta="center" py="xl">No students match your search.</Text>
            ) : (
            <Card withBorder padding="0" style={{ opacity: overviewQuery.isFetching ? 0.6 : 1 }}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Student</Table.Th>
                    <Table.Th>Class group</Table.Th>
                    <Table.Th
                      ta="center"
                      style={{ cursor: 'pointer', userSelect: 'none' }}
                      onClick={() =>
                        setAvgSort((s) => (s === 'desc' ? 'asc' : s === 'asc' ? null : 'desc'))
                      }
                    >
                      <Group gap={4} justify="center" wrap="nowrap">
                        Assessment avg
                        {avgSort === 'desc' ? (
                          <IconArrowDown size={14} />
                        ) : avgSort === 'asc' ? (
                          <IconArrowUp size={14} />
                        ) : (
                          <IconArrowsSort size={14} style={{ opacity: 0.5 }} />
                        )}
                      </Group>
                    </Table.Th>
                    <Table.Th ta="right">{MONTH_NAMES[month - 1]} time</Table.Th>
                    <Table.Th ta="center">Days active (all-time)</Table.Th>
                    <Table.Th ta="right">Total time (all-time)</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {sortedRows.map((r) => (
                    <Table.Tr key={r.student_id}>
                      <Table.Td>
                        <Text fw={600} size="sm">{r.name || r.email}</Text>
                        {r.name && <Text size="xs" c="dimmed">{r.email}</Text>}
                      </Table.Td>
                      <Table.Td>{r.class_group || <Text c="dimmed" size="sm">—</Text>}</Table.Td>
                      <Table.Td ta="center">
                        {r.avg_assessment_score == null ? (
                          <Text c="dimmed" size="sm">—</Text>
                        ) : (
                          <Badge color={scoreColor(r.avg_assessment_score)} variant="light">
                            {r.avg_assessment_score}%
                          </Badge>
                        )}
                      </Table.Td>
                      <Table.Td ta="right">
                        <Text size="sm" c={r.total_seconds > 0 ? undefined : 'dimmed'}>
                          {formatDuration(r.total_seconds)}
                        </Text>
                      </Table.Td>
                      <Table.Td ta="center">
                        <Badge variant="light">{r.all_time_active_days}</Badge>
                      </Table.Td>
                      <Table.Td ta="right">
                        <Text fw={700} size="sm">{formatDuration(r.all_time_seconds)}</Text>
                      </Table.Td>
                      <Table.Td ta="right">
                        <Group gap="xs" justify="flex-end" wrap="nowrap">
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
                          <Button
                            size="compact-sm"
                            variant="light"
                            color="teal"
                            leftSection={<IconReportAnalytics size={14} />}
                            onClick={() => setReportStudent({ id: r.student_id, name: r.name || r.email })}
                          >
                            Report
                          </Button>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Card>
            )}
            </>
          )}

        </Stack>

        {/* Daily platform-time breakdown, in a right-side panel. */}
        <Drawer
          opened={selected !== null}
          onClose={() => setSelected(null)}
          title={<Text fw={600}>{selected?.name} — daily breakdown</Text>}
          position="right"
          size="lg"
          scrollAreaComponent={ScrollArea.Autosize}
        >
          <Stack gap="sm">
            {detailQuery.data && (
              <Text size="sm" c="dimmed">
                All-time:{' '}
                <Text span fw={700} c="var(--mantine-color-text)">
                  {formatDuration(detailQuery.data.all_time_seconds)}
                </Text>{' '}
                over {detailQuery.data.all_time_active_days} day
                {detailQuery.data.all_time_active_days === 1 ? '' : 's'}
              </Text>
            )}
            {detailQuery.isLoading ? (
              <Group justify="center" py="md"><Loader size="sm" /></Group>
            ) : (
              <PlatformUsageTable
                days={detailQuery.data?.days ?? []}
                totalSeconds={detailQuery.data?.total_seconds ?? 0}
                loading={detailQuery.isFetching}
              />
            )}
          </Stack>
        </Drawer>

        <StudentReportDrawer student={reportStudent} onClose={() => setReportStudent(null)} />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
