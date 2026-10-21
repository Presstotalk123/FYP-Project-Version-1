'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Group, Loader, Table, Text } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { leaderboardService } from '@/services/leaderboard.service';
import { queryKeys } from '@/services/query-keys';
import {
  ClassGroupSelect, LeaderboardPager, MyRankText, RankBadge, ROW_ME_STYLE, apiErrorDetail, usePagedRows,
} from './shared';

export function OverallLeaderboard({ showEmail }: { showEmail: boolean }) {
  const [classGroup, setClassGroup] = useState<string | null>(null);

  const boardQuery = useQuery({
    queryKey: queryKeys.overallLeaderboard(classGroup),
    queryFn: () => leaderboardService.getOverallLeaderboard(classGroup),
    placeholderData: (prev) => prev,
  });
  const board = boardQuery.data;
  const rows = board?.rows ?? [];
  const paged = usePagedRows(rows, classGroup ?? '');
  const myIndex = rows.findIndex((r) => r.is_me);

  return (
    <>
      <Group gap="sm" align="flex-end">
        <ClassGroupSelect groups={board?.class_groups ?? []} value={classGroup} onChange={setClassGroup} />
        <Text c="dimmed" size="sm" pb={6}>
          Total = SQL questions + ER questions + labs completed (same counts as the Report page).
        </Text>
      </Group>

      {boardQuery.isLoading ? (
        <Group justify="center" py="xl"><Loader /></Group>
      ) : boardQuery.error ? (
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="Failed to load leaderboard">
          {apiErrorDetail(boardQuery.error, 'Could not load the overall leaderboard.')}
        </Alert>
      ) : !board || board.rows.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">No students to show.</Text>
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
                  <Table.Th ta="center">SQL</Table.Th>
                  <Table.Th ta="center">ER</Table.Th>
                  <Table.Th ta="center">Labs</Table.Th>
                  <Table.Th ta="right">Total</Table.Th>
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
                    <Table.Td ta="center">{r.sql_completed}</Table.Td>
                    <Table.Td ta="center">{r.erd_completed}</Table.Td>
                    <Table.Td ta="center">{r.labs_completed}</Table.Td>
                    <Table.Td ta="right"><Text fw={700} size="sm">{r.total}</Text></Table.Td>
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
