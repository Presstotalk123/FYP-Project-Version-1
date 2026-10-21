'use client';

import { useState, type CSSProperties } from 'react';
import { Anchor, Badge, Center, Group, Pagination, Select, Text } from '@mantine/core';

// Highlight for the viewing student's own row: a light tint of --brand-lilac.
export const ROW_ME_STYLE: CSSProperties = {
  backgroundColor: 'rgba(132, 88, 179, 0.12)',
};

const MEDAL_COLORS: Record<number, string> = { 1: 'yellow', 2: 'gray', 3: 'orange' };

// Width of a size="lg" circle Badge, so plain ranks centre under the medals.
const RANK_CELL_WIDTH = 26;

/** Gold / silver / bronze badge for the top 3, plain number otherwise. */
export function RankBadge({ rank }: { rank: number }) {
  const color = MEDAL_COLORS[rank];
  return (
    <Center w={RANK_CELL_WIDTH}>
      {color ? (
        <Badge color={color} variant="filled" circle size="lg">{rank}</Badge>
      ) : (
        <Text size="sm" fw={600}>{rank}</Text>
      )}
    </Center>
  );
}

/** "All class groups" plus each group. `null` means all. */
export function ClassGroupSelect({ groups, value, onChange }: {
  groups: string[];
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  return (
    <Select
      label="Class group"
      data={[{ value: '', label: 'All class groups' }, ...groups.map((g) => ({ value: g, label: g }))]}
      value={value ?? ''}
      onChange={(v) => onChange(v ? v : null)}
      allowDeselect={false}
      w={200}
    />
  );
}

/**
 * "Your rank: #N of M", shown only to a student who is listed. With `onJump`, the
 * rank is a link that pages the table to the student's own row.
 */
export function MyRankText({ myRank, total, onJump }: {
  myRank: number | null;
  total: number;
  onJump?: () => void;
}) {
  if (myRank === null) return null;
  const rank = <Text span c="var(--brand-lilac)" fw={800}>#{myRank}</Text>;
  return (
    <Text fw={600}>
      Your rank:{' '}
      {onJump ? (
        <Anchor component="button" type="button" onClick={onJump} title="Go to your row">{rank}</Anchor>
      ) : rank}
      {' '}of {total}
    </Text>
  );
}

const PAGE_SIZES = [10, 25, 50];

export interface PagedRows<T> {
  visible: T[];
  /** Index in the full list of the first visible row. */
  start: number;
  total: number;
  page: number;
  totalPages: number;
  pageSize: number;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  /** Page to the row at this index in the full list. */
  goToRow: (index: number) => void;
}

/**
 * Client-side paging over an already-ranked list (ranks come from the server, so
 * they stay correct on every page). Returns to page 1 whenever `resetKey` changes,
 * e.g. a different lab or class group, so the viewer never lands on an empty page.
 */
export function usePagedRows<T>(rows: T[], resetKey: string): PagedRows<T> {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeState] = useState(PAGE_SIZES[0]);
  const [lastKey, setLastKey] = useState(resetKey);
  if (lastKey !== resetKey) {
    setLastKey(resetKey);
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, totalPages);
  const start = (current - 1) * pageSize;
  return {
    visible: rows.slice(start, start + pageSize),
    start,
    total: rows.length,
    page: current,
    totalPages,
    pageSize,
    setPage,
    setPageSize: (size) => {
      setPageSizeState(size);
      setPage(1);
    },
    goToRow: (index) => setPage(Math.floor(index / pageSize) + 1),
  };
}

/** "Showing X–Y of N", page buttons and a rows-per-page picker. Hidden when one page fits all. */
export function LeaderboardPager<T>({ paged }: { paged: PagedRows<T> }) {
  if (paged.total <= PAGE_SIZES[0]) return null;
  return (
    <Group justify="space-between" gap="sm">
      <Text size="sm" c="dimmed">
        Showing {paged.start + 1}–{paged.start + paged.visible.length} of {paged.total}
      </Text>
      <Pagination total={paged.totalPages} value={paged.page} onChange={paged.setPage} size="sm" />
      <Group gap="xs">
        <Text size="sm" c="dimmed">Rows per page</Text>
        <Select
          data={PAGE_SIZES.map(String)}
          value={String(paged.pageSize)}
          onChange={(v) => v && paged.setPageSize(Number(v))}
          allowDeselect={false}
          size="xs"
          w={80}
        />
      </Group>
    </Group>
  );
}

export function apiErrorDetail(error: unknown, fallback: string): string {
  return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? fallback;
}
