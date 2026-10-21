'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Badge, Card, Group, Loader, Select, Table, Text, Tooltip } from '@mantine/core';
import { IconAlertCircle, IconEyeOff } from '@tabler/icons-react';
import { useAuth } from '@/contexts/AuthContext';
import { labService } from '@/services/lab.service';
import { leaderboardService } from '@/services/leaderboard.service';
import { queryKeys } from '@/services/query-keys';
import { LabTaskStatus } from '@/types/leaderboard.types';
import {
  ClassGroupSelect, LeaderboardPager, MyRankText, RankBadge, ROW_ME_STYLE, apiErrorDetail, usePagedRows,
} from './shared';

const TASK_MARK: Record<LabTaskStatus, { mark: string; color: string; label: string }> = {
  solved: { mark: '✓', color: 'green', label: 'Solved' },
  attempted: { mark: '✗', color: 'red', label: 'Attempted, not solved' },
  not_attempted: { mark: '–', color: 'dimmed', label: 'Not attempted' },
};

function formatFinished(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

export function LabLeaderboard({ showEmail }: { showEmail: boolean }) {
  const { isStaff } = useAuth();
  const [pickedLabId, setPickedLabId] = useState<number | null>(null);
  const [classGroup, setClassGroup] = useState<string | null>(null);

  // Reuse the lab list the Labs pages already cache: the backend returns only
  // published labs to students, all non-deleted bank labs to staff.
  const labsQuery = useQuery({
    queryKey: isStaff ? queryKeys.labs : queryKeys.studentLabs,
    queryFn: () => labService.getLabs(),
  });
  const labs = labsQuery.data ?? [];
  const labId = pickedLabId ?? labs[0]?.id ?? null;

  const boardQuery = useQuery({
    queryKey: labId !== null ? queryKeys.labLeaderboard(labId, classGroup) : ['labLeaderboard', 'none'],
    queryFn: () => leaderboardService.getLabLeaderboard(labId!, classGroup),
    enabled: labId !== null,
    placeholderData: (prev) => prev,
  });
  const board = boardQuery.data;
  const rows = board?.rows ?? [];
  const paged = usePagedRows(rows, `${labId}|${classGroup ?? ''}`);
  const myIndex = rows.findIndex((r) => r.is_me);

  const labOptions = [
    { group: 'SQL Labs', items: labs.filter((l) => l.lab_type !== 'graph').map((l) => ({ value: String(l.id), label: l.title })) },
    { group: 'Graph Labs', items: labs.filter((l) => l.lab_type === 'graph').map((l) => ({ value: String(l.id), label: l.title })) },
  ].filter((g) => g.items.length > 0);

  if (labsQuery.isLoading) {
    return <Group justify="center" py="xl"><Loader /></Group>;
  }
  if (labsQuery.error) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" title="Failed to load labs">
        {apiErrorDetail(labsQuery.error, 'Could not load the lab list.')}
      </Alert>
    );
  }
  if (labs.length === 0) {
    return <Text c="dimmed" ta="center" py="xl">No labs available yet.</Text>;
  }

  return (
    <>
      <Group gap="sm" align="flex-end">
        <Select
          label="Lab"
          data={labOptions}
          value={labId !== null ? String(labId) : null}
          onChange={(v) => v && setPickedLabId(Number(v))}
          allowDeselect={false}
          searchable
          w={320}
        />
        <ClassGroupSelect groups={board?.class_groups ?? []} value={classGroup} onChange={setClassGroup} />
      </Group>

      {boardQuery.isLoading ? (
        <Group justify="center" py="xl"><Loader /></Group>
      ) : boardQuery.error ? (
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="Failed to load leaderboard">
          {apiErrorDetail(boardQuery.error, 'Could not load the leaderboard for this lab.')}
        </Alert>
      ) : !board ? null : board.correctness_hidden ? (
        <Alert icon={<IconEyeOff size={16} />} color="gray" title="Results hidden">
          Your instructor has hidden results for this lab, so its leaderboard isn&apos;t shown.
        </Alert>
      ) : board.tasks.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">This lab has no tasks yet.</Text>
      ) : board.rows.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">No one has submitted to this lab yet.</Text>
      ) : (
        <>
          <MyRankText
            myRank={board.my_rank}
            total={board.rows.length}
            onJump={myIndex >= 0 ? () => paged.goToRow(myIndex) : undefined}
          />
          <Card withBorder padding="0" style={{ opacity: boardQuery.isFetching ? 0.6 : 1, overflowX: 'auto' }}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Rank</Table.Th>
                  <Table.Th>Student</Table.Th>
                  <Table.Th>Class group</Table.Th>
                  {board.tasks.map((t, i) => (
                    <Table.Th key={t.task_id} ta="center">
                      <Tooltip label={t.title} withArrow>
                        <span style={{ cursor: 'help' }}>T{i + 1}</span>
                      </Tooltip>
                    </Table.Th>
                  ))}
                  <Table.Th ta="center">Tasks</Table.Th>
                  <Table.Th ta="center">Submissions</Table.Th>
                  <Table.Th ta="right">Finished</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {paged.visible.map((r, idx) => (
                  <Table.Tr key={r.student_id ?? `row-${paged.start + idx}`} style={r.is_me ? ROW_ME_STYLE : undefined}>
                    <Table.Td><RankBadge rank={r.rank} /></Table.Td>
                    <Table.Td>
                      <Text fw={600} size="sm">{r.display_name}{r.is_me && ' (you)'}</Text>
                      {showEmail && r.email && r.email !== r.display_name && (
                        <Text size="xs" c="dimmed">{r.email}</Text>
                      )}
                    </Table.Td>
                    <Table.Td>{r.class_group || <Text c="dimmed" size="sm">—</Text>}</Table.Td>
                    {r.task_status.map((s, i) => (
                      <Table.Td key={board.tasks[i].task_id} ta="center">
                        <Tooltip label={TASK_MARK[s].label} withArrow>
                          <Text span fw={700} c={TASK_MARK[s].color}>{TASK_MARK[s].mark}</Text>
                        </Tooltip>
                      </Table.Td>
                    ))}
                    <Table.Td ta="center">
                      <Group gap={6} justify="center" wrap="nowrap">
                        <Text size="sm" fw={700}>{r.tasks_correct}/{r.total_tasks}</Text>
                        {r.completed && <Badge color="green" variant="light" size="sm">Completed</Badge>}
                      </Group>
                    </Table.Td>
                    <Table.Td ta="center">{r.submissions}</Table.Td>
                    <Table.Td ta="right">
                      <Text size="sm" c={r.finished_at ? undefined : 'dimmed'}>{formatFinished(r.finished_at)}</Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Card>
          <LeaderboardPager paged={paged} />
        </>
      )}
    </>
  );
}
