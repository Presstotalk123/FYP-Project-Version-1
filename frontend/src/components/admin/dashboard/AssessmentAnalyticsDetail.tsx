'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { assessmentService } from '@/services/assessment.service';
import { queryKeys } from '@/services/query-keys';
import { AssessmentItemAggregateScore, ItemStudentRow } from '@/types/assessment.types';

const ITEM_TYPE_LABEL: Record<string, string> = {
  sql_question: 'SQL Question',
  er_question: 'ER Question',
  sql_lab: 'SQL Lab',
  graph_lab: 'Graph Lab',
};

// An item's average as a 0-100 percentage, or null when the roster is empty.
function itemPercent(item: AssessmentItemAggregateScore): number | null {
  if (item.avg_score_fraction == null) return null;
  return Math.round(item.avg_score_fraction * 1000) / 10;
}

function renderScore(score: number | null | undefined) {
  if (score == null) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  const cls = score >= 75 ? 'badge-success' : score >= 50 ? 'badge-warn' : 'badge-danger';
  return <span className={`badge ${cls}`}>{score}%</span>;
}

// Signed delta with direction. Null when either side is missing, so an unweighted
// assessment shows nothing rather than a fake 0.0.
function renderDelta(group: number | null, cohort: number | null) {
  if (group == null || cohort == null) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  const delta = Math.round((group - cohort) * 10) / 10;
  if (delta === 0) return <span style={{ color: 'var(--text-muted)' }}>0.0</span>;
  const up = delta > 0;
  return (
    <span style={{ color: up ? 'var(--success)' : 'var(--error)', fontWeight: 700 }}>
      {up ? '+' : ''}{delta} {up ? '▲' : '▼'}
    </span>
  );
}

const STATUS_LABEL: Record<string, string> = {
  not_started: 'Not started',
  not_attempted: 'Not attempted',
  graded: '',
};

// The expanded student list for one question. Fetches only while open; the query key
// includes the class group so each group caches separately.
function QuestionStudentList({
  assessmentId,
  itemId,
  classGroup,
  colSpan,
}: {
  assessmentId: number;
  itemId: number;
  classGroup: string | null;
  colSpan: number;
}) {
  const query = useQuery({
    queryKey: queryKeys.assessmentItemStudents(assessmentId, itemId, classGroup),
    queryFn: () => assessmentService.getItemStudents(assessmentId, itemId, classGroup),
  });

  const renderCell = (row: ItemStudentRow) => {
    if (row.status === 'not_started') {
      return <span style={{ color: 'var(--text-muted)' }}>—</span>;
    }
    const pct = row.score_percent ?? 0;
    const cls = pct >= 75 ? 'badge-success' : pct >= 50 ? 'badge-warn' : 'badge-danger';
    return <span className={`badge ${cls}`}>{pct}%</span>;
  };

  return (
    <tr>
      <td colSpan={colSpan} style={{ background: 'var(--surface-muted)', padding: '10px 14px' }}>
        {query.isLoading && <span style={{ color: 'var(--text-muted)' }}>Loading students…</span>}

        {query.error != null && (
          <span style={{ color: 'var(--error)' }}>Failed to load students for this question.</span>
        )}

        {query.data && query.data.students.length === 0 && (
          <span style={{ color: 'var(--text-muted)' }}>No students registered for this group.</span>
        )}

        {query.data && query.data.students.length > 0 && (
          <>
            {/* Counts the rows actually rendered, not registered_count: the list is the union
                of registered students and the roster, so the two can differ and the header
                would otherwise claim "5 registered" above 7 rows. */}
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
              {query.data.students.length} student{query.data.students.length === 1 ? '' : 's'} · weakest first
            </div>
            <table className="da-table" style={{ background: 'transparent' }}>
              <tbody>
                {query.data.students.map((row) => (
                  <tr key={row.email}>
                    <td style={{ width: '45%' }}>{row.name || row.email}</td>
                    <td style={{ width: '15%' }}>{row.class_group ?? '—'}</td>
                    <td style={{ width: '15%' }}>{renderCell(row)}</td>
                    <td style={{ color: 'var(--text-muted)' }}>
                      {STATUS_LABEL[row.status] || row.detail || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </td>
    </tr>
  );
}

export function AssessmentAnalyticsDetail({
  assessmentId,
  onBack,
}: {
  assessmentId: number;
  onBack: () => void;
}) {
  const [classGroup, setClassGroup] = useState<string | null>(null);
  // One question expanded at a time — opening a second collapses the first, so the page
  // never becomes a wall of student lists.
  const [expandedItemId, setExpandedItemId] = useState<number | null>(null);

  const cohortQuery = useQuery({
    queryKey: queryKeys.assessmentItemAnalytics(assessmentId, null),
    queryFn: () => assessmentService.getAssessmentItemAnalytics(assessmentId, null),
  });

  const groupQuery = useQuery({
    queryKey: queryKeys.assessmentItemAnalytics(assessmentId, classGroup),
    queryFn: () => assessmentService.getAssessmentItemAnalytics(assessmentId, classGroup),
    enabled: classGroup !== null,
  });

  // Group options ride along on the analytics response, already scoped to this assessment's
  // roster. Previously this fetched the entire student roster — every row with its scores —
  // purely to populate a dropdown, which cost a second request and ~8 backend queries.
  const groupOptions = cohortQuery.data?.class_groups ?? [];

  if (cohortQuery.isLoading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
        <span>Loading analytics…</span>
      </div>
    );
  }

  if (cohortQuery.error) {
    const err = cohortQuery.error as { response?: { data?: { detail?: string } } };
    return (
      <>
        <button className="btn btn-secondary" onClick={onBack}>‹ Back</button>
        <div className="da-alert alert-error" role="alert" style={{ marginTop: 12 }}>
          <strong>Error</strong>
          <span>{err.response?.data?.detail || 'Failed to load analytics'}</span>
        </div>
      </>
    );
  }

  const cohort = cohortQuery.data;
  if (!cohort) return null;

  const group = classGroup ? groupQuery.data : undefined;
  const comparing = classGroup !== null && !!group;
  const scoped = group ?? cohort;

  return (
    <>
      <div className="page-head">
        <div>
          <button className="btn btn-secondary" onClick={onBack}>‹ Back</button>
          <h2 style={{ marginTop: 10 }}>{cohort.assessment_title}</h2>
        </div>
        <div className="button-row">
          <select
            className="btn btn-secondary"
            value={classGroup ?? ''}
            onChange={(e) => setClassGroup(e.target.value || null)}
            aria-label="Tutorial group"
          >
            <option value="">All (cohort)</option>
            {groupOptions.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        </div>
      </div>

      {classGroup && groupQuery.isLoading && (
        <div className="loading-center">
          <div className="spinner" />
          <span>Loading {classGroup}…</span>
        </div>
      )}

      {/* Without this the failure is silent: `comparing` goes false, the table falls back to
          cohort-wide figures headed "Cohort", and the dropdown still reads the group name —
          so staff would be looking at the wrong numbers with no indication anything failed. */}
      {classGroup && groupQuery.error != null && (
        <div className="da-alert alert-error" role="alert">
          <strong>Could not load {classGroup}</strong>
          <span>Showing cohort-wide figures instead. Re-select the group to retry.</span>
        </div>
      )}

      {comparing && scoped.student_count === 0 && (
        <div className="da-alert alert-info">
          <strong>No students in {classGroup}</strong>
          <span>Nobody from this tutorial group has started this assessment.</span>
        </div>
      )}

      <div className="table-wrap" style={{ marginBottom: 18 }}>
        <table className="da-table">
          <thead>
            <tr>
              <th>{comparing ? classGroup : 'Cohort'}</th>
              <th>Average</th>
              {comparing && <th>Cohort</th>}
              {comparing && <th>Δ</th>}
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ fontWeight: 700 }}>Overall</td>
              <td>{renderScore(scoped.avg_weighted_score)}</td>
              {comparing && <td>{renderScore(cohort.avg_weighted_score)}</td>}
              {comparing && (
                <td>{renderDelta(scoped.avg_weighted_score ?? null, cohort.avg_weighted_score ?? null)}</td>
              )}
              <td>{scoped.student_count}/{scoped.registered_count ?? 0}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {cohort.items.length === 0 ? (
        <div className="da-alert alert-info">
          <strong>No questions</strong>
          <span>This assessment has no questions in it.</span>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="da-table">
            <thead>
              <tr>
                <th>Question</th>
                <th>Average</th>
                {comparing && <th>Cohort</th>}
                {comparing && <th>Δ</th>}
                <th>Attempted</th>
              </tr>
            </thead>
            <tbody>
              {scoped.items.map((item, idx) => {
                const cohortItem = cohort.items.find(
                  (c) => c.assessment_item_id === item.assessment_item_id,
                );
                const denominator = scoped.registered_count ?? 0;
                const expanded = expandedItemId === item.assessment_item_id;
                const colSpan = comparing ? 5 : 3;
                return (
                  <React.Fragment key={item.assessment_item_id}>
                    <tr
                      style={{ cursor: 'pointer' }}
                      onClick={() =>
                        setExpandedItemId(expanded ? null : item.assessment_item_id)
                      }
                    >
                      <td>
                        <span style={{ color: 'var(--text-muted)', marginRight: 6 }}>
                          {expanded ? '▾' : '▸'}
                        </span>
                        <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>#{idx + 1}</span>
                        <span className="badge badge-info" style={{ marginRight: 8 }}>
                          {ITEM_TYPE_LABEL[item.item_type] ?? item.item_type}
                        </span>
                        {item.item_title}
                      </td>
                      <td>{renderScore(itemPercent(item))}</td>
                      {comparing && <td>{renderScore(cohortItem ? itemPercent(cohortItem) : null)}</td>}
                      {comparing && (
                        <td>
                          {renderDelta(
                            itemPercent(item),
                            cohortItem ? itemPercent(cohortItem) : null,
                          )}
                        </td>
                      )}
                      <td>
                        {item.attempted_count ?? 0}/{denominator}
                      </td>
                    </tr>
                    {expanded && (
                      <QuestionStudentList
                        assessmentId={assessmentId}
                        itemId={item.assessment_item_id}
                        classGroup={classGroup}
                        colSpan={colSpan}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
