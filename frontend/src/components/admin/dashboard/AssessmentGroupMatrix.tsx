'use client';

import { useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { assessmentService } from '@/services/assessment.service';
import { queryKeys } from '@/services/query-keys';
import { AssessmentItemAggregateScore } from '@/types/assessment.types';

// A 0-100 percentage from an item's mean correctness fraction, or null when the roster
// is empty. Mirrors itemPercent in AssessmentAnalyticsDetail.
function fractionToPercent(fraction: number | null | undefined): number | null {
  if (fraction == null) return null;
  return Math.round(fraction * 1000) / 10;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function renderScore(score: number | null | undefined) {
  if (score == null) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  const cls = score >= 75 ? 'badge-success' : score >= 50 ? 'badge-warn' : 'badge-danger';
  return <span className={`badge ${cls}`}>{score}%</span>;
}

// Mean of the non-null values, or null when they're all null.
function meanOrNull(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => v != null);
  if (present.length === 0) return null;
  return round1(present.reduce((a, b) => a + b, 0) / present.length);
}

export function AssessmentGroupMatrix({
  assessmentId,
  groups,
  items,
}: {
  assessmentId: number;
  groups: string[];
  items: AssessmentItemAggregateScore[];
}) {
  // Column sort: which column ('total' or a question's column index) and direction.
  // null = roster order. Only one column is active at a time; the Average row stays pinned.
  const [sort, setSort] = useState<{ col: number | 'total'; dir: 'asc' | 'desc' } | null>(null);
  // Cycle a column: none/other → desc → asc → none.
  const cycleSort = (col: number | 'total') =>
    setSort((s) =>
      !s || s.col !== col ? { col, dir: 'desc' } : s.dir === 'desc' ? { col, dir: 'asc' } : null,
    );
  const sortArrow = (col: number | 'total') =>
    sort && sort.col === col ? (sort.dir === 'desc' ? '↓' : '↑') : '⇅';

  // One analytics call per class group. Reuses the same query keys as the per-question
  // dropdown, so a group already viewed there is served from cache.
  const groupQueries = useQueries({
    queries: groups.map((group) => ({
      queryKey: queryKeys.assessmentItemAnalytics(assessmentId, group),
      queryFn: () => assessmentService.getAssessmentItemAnalytics(assessmentId, group),
    })),
  });

  if (groups.length === 0) {
    return (
      <div className="da-alert alert-info">
        <strong>No class groups</strong>
        <span>This assessment&apos;s roster has no class groups to break down.</span>
      </div>
    );
  }

  const anyLoading = groupQueries.some((q) => q.isPending);
  if (anyLoading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
        <span>Loading group breakdown…</span>
      </div>
    );
  }

  const anyError = groupQueries.some((q) => q.error != null);

  // Column order + labels come from the cohort's questions (already ordered by order_index).
  const columns = items;

  // Build one row per group: a per-question percent lookup plus the group's overall Total.
  const rows = groups.map((group, i) => {
    const data = groupQueries[i].data;
    const cellByItem = new Map<number, number | null>();
    for (const item of data?.items ?? []) {
      cellByItem.set(item.assessment_item_id, fractionToPercent(item.avg_score_fraction));
    }
    return {
      group,
      cells: columns.map((c) => cellByItem.get(c.assessment_item_id) ?? null),
      total: data?.avg_weighted_score != null ? round1(data.avg_weighted_score) : null,
      failed: groupQueries[i].error != null,
    };
  });

  // Bottom "Average" row: mean of each column across the group rows, plus mean of the
  // Total column. Matches the displayed numbers rather than the student-weighted cohort.
  const columnAverages = columns.map((_, colIdx) =>
    meanOrNull(rows.map((r) => r.cells[colIdx])),
  );
  const totalAverage = meanOrNull(rows.map((r) => r.total));

  // Sort the group rows by the active column; groups with no value (—) sort last. The
  // Average row is rendered separately and always stays at the bottom.
  const valueFor = (row: (typeof rows)[number], col: number | 'total') =>
    col === 'total' ? row.total : row.cells[col];
  const sortedRows =
    sort === null
      ? rows
      : [...rows].sort((a, b) => {
          const sa = valueFor(a, sort.col);
          const sb = valueFor(b, sort.col);
          if (sa == null && sb == null) return 0;
          if (sa == null) return 1;
          if (sb == null) return -1;
          return sort.dir === 'desc' ? sb - sa : sa - sb;
        });

  return (
    <>
      {anyError && (
        <div className="da-alert alert-error" role="alert" style={{ marginBottom: 12 }}>
          <strong>Some groups failed to load</strong>
          <span>Rows marked with — could not be fetched. Reopen this view to retry.</span>
        </div>
      )}
      <div className="table-wrap">
        <table className="da-table">
          <thead>
            <tr>
              <th>Group</th>
              {columns.map((c, idx) => (
                <th
                  key={c.assessment_item_id}
                  title={c.item_title}
                  style={{ cursor: 'pointer', userSelect: 'none' }}
                  onClick={() => cycleSort(idx)}
                >
                  Q{idx + 1}{' '}
                  <span style={{ color: 'var(--text-muted)' }}>{sortArrow(idx)}</span>
                </th>
              ))}
              <th
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => cycleSort('total')}
              >
                Total{' '}
                <span style={{ color: 'var(--text-muted)' }}>{sortArrow('total')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr key={row.group}>
                <td style={{ fontWeight: 600 }}>{row.group}</td>
                {row.cells.map((cell, idx) => (
                  <td key={columns[idx].assessment_item_id}>{renderScore(cell)}</td>
                ))}
                <td>{renderScore(row.total)}</td>
              </tr>
            ))}
            <tr style={{ borderTop: '2px solid var(--border)' }}>
              <td style={{ fontWeight: 700 }}>Average</td>
              {columnAverages.map((avg, idx) => (
                <td key={columns[idx].assessment_item_id} style={{ fontWeight: 600 }}>
                  {renderScore(avg)}
                </td>
              ))}
              <td style={{ fontWeight: 600 }}>{renderScore(totalAverage)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
