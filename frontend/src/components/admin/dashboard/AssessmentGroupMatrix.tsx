'use client';

import { Fragment, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
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
  // Which group row is expanded to its per-student component scores (one at a time).
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
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
            {sortedRows.map((row) => {
              const expanded = expandedGroup === row.group;
              return (
                <Fragment key={row.group}>
                  <tr
                    style={{ cursor: 'pointer' }}
                    onClick={() => setExpandedGroup(expanded ? null : row.group)}
                  >
                    <td style={{ fontWeight: 600 }}>
                      <span style={{ color: 'var(--text-muted)', marginRight: 6 }}>
                        {expanded ? '▾' : '▸'}
                      </span>
                      {row.group}
                    </td>
                    {row.cells.map((cell, idx) => (
                      <td key={columns[idx].assessment_item_id}>{renderScore(cell)}</td>
                    ))}
                    <td>{renderScore(row.total)}</td>
                  </tr>
                  {expanded && (
                    <tr>
                      <td
                        colSpan={columns.length + 2}
                        style={{ background: 'var(--surface-muted)', padding: '10px 14px' }}
                      >
                        <GroupStudentBreakdown
                          assessmentId={assessmentId}
                          group={row.group}
                          columns={columns}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
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

// The per-student breakdown shown when a group row is expanded: every student in the
// group with their score on each component and their overall total. Component cells come
// from one getItemStudents call per column (pivoted by email); totals come from the
// assessment-wide student list.
function GroupStudentBreakdown({
  assessmentId,
  group,
  columns,
}: {
  assessmentId: number;
  group: string;
  columns: AssessmentItemAggregateScore[];
}) {
  // Column sort within this group's students. null = default (highest Total first).
  const [sort, setSort] = useState<{ col: number | 'total'; dir: 'asc' | 'desc' } | null>(null);
  const cycleSort = (col: number | 'total') =>
    setSort((s) =>
      !s || s.col !== col ? { col, dir: 'desc' } : s.dir === 'desc' ? { col, dir: 'asc' } : null,
    );
  const sortArrow = (col: number | 'total') =>
    sort && sort.col === col ? (sort.dir === 'desc' ? '↓' : '↑') : '⇅';

  const itemQueries = useQueries({
    queries: columns.map((col) => ({
      queryKey: queryKeys.assessmentItemStudents(assessmentId, col.assessment_item_id, group),
      queryFn: () => assessmentService.getItemStudents(assessmentId, col.assessment_item_id, group),
    })),
  });
  const studentsQuery = useQuery({
    queryKey: queryKeys.assessmentStudents(assessmentId),
    queryFn: () => assessmentService.getAssessmentStudents(assessmentId),
  });

  if (itemQueries.some((q) => q.isPending) || studentsQuery.isPending) {
    return (
      <div className="loading-center">
        <div className="spinner" />
        <span>Loading students…</span>
      </div>
    );
  }

  const anyError = itemQueries.some((q) => q.error != null) || studentsQuery.error != null;

  // Per-column lookup of each student's score on that question, keyed by email.
  const cellByColumn = itemQueries.map((q) => {
    const map = new Map<string, number | null>();
    for (const s of q.data?.students ?? []) {
      map.set(s.email, s.status === 'not_started' ? null : s.score_percent ?? null);
    }
    return map;
  });

  const roster = (studentsQuery.data?.students ?? []).filter((s) => s.class_group === group);

  if (roster.length === 0) {
    return (
      <div className="da-alert alert-info">
        <strong>No students</strong>
        <span>No students in this group.</span>
      </div>
    );
  }

  const baseRows = roster.map((s) => ({
    name: s.name || s.email,
    email: s.email,
    cells: columns.map((_, idx) => cellByColumn[idx].get(s.email) ?? null),
    total: s.weighted_score ?? null,
  }));

  // Default (no active column) = highest Total first; otherwise sort by the active column.
  // Students with no value in the sort column always sort last.
  const valueFor = (row: (typeof baseRows)[number], col: number | 'total') =>
    col === 'total' ? row.total : row.cells[col];
  const sortCol: number | 'total' = sort ? sort.col : 'total';
  const sortDir: 'asc' | 'desc' = sort ? sort.dir : 'desc';
  const rows = [...baseRows].sort((a, b) => {
    const va = valueFor(a, sortCol);
    const vb = valueFor(b, sortCol);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return sortDir === 'desc' ? vb - va : va - vb;
  });

  return (
    <>
      {anyError && (
        <div className="da-alert alert-error" role="alert" style={{ marginBottom: 8 }}>
          <strong>Some scores failed to load</strong>
          <span>Cells marked with — could not be fetched. Collapse and reopen to retry.</span>
        </div>
      )}
      <div className="table-wrap">
        <table className="da-table" style={{ background: 'transparent' }}>
          <thead>
            <tr>
              <th>Student</th>
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
            {rows.map((row) => (
              <tr key={row.email}>
                <td title={row.email}>{row.name}</td>
                {row.cells.map((cell, idx) => (
                  <td key={columns[idx].assessment_item_id}>{renderScore(cell)}</td>
                ))}
                <td>{renderScore(row.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
