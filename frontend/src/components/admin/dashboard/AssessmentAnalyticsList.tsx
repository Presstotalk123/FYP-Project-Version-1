'use client';

import { useQuery } from '@tanstack/react-query';
import { assessmentService } from '@/services/assessment.service';
import { queryKeys } from '@/services/query-keys';

// Colour a 0-100 score like a gradebook, matching the assessment students page.
function scoreBadgeClass(score: number): string {
  if (score >= 75) return 'badge-success';
  if (score >= 50) return 'badge-warn';
  return 'badge-danger';
}

function renderScore(score: number | null | undefined) {
  if (score == null) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  return <span className={`badge ${scoreBadgeClass(score)}`}>{score}%</span>;
}

export function AssessmentAnalyticsList({
  onSelect,
}: {
  onSelect: (assessmentId: number) => void;
}) {
  const summaryQuery = useQuery({
    queryKey: queryKeys.assessmentAnalyticsSummary,
    queryFn: () => assessmentService.getAnalyticsSummary(),
  });

  if (summaryQuery.isLoading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
        <span>Loading assessments…</span>
      </div>
    );
  }

  if (summaryQuery.error) {
    const err = summaryQuery.error as { response?: { data?: { detail?: string } } };
    return (
      <div className="da-alert alert-error" role="alert">
        <strong>Error</strong>
        <span>{err.response?.data?.detail || 'Failed to load assessment analytics'}</span>
      </div>
    );
  }

  const rows = summaryQuery.data?.assessments ?? [];

  if (rows.length === 0) {
    return (
      <div className="da-alert alert-info">
        <strong>No assessments</strong>
        <span>Create an assessment to see its analytics here.</span>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="da-table">
        <thead>
          <tr>
            <th>Assessment</th>
            <th>Average</th>
            <th>Started</th>
            <th>Questions</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.assessment_id}
              style={{ cursor: 'pointer' }}
              onClick={() => onSelect(row.assessment_id)}
            >
              <td>
                {row.title}
                {!row.is_published && (
                  <span className="badge neutral" style={{ marginLeft: 8 }}>Draft</span>
                )}
              </td>
              <td>{renderScore(row.avg_weighted_score)}</td>
              <td>
                {row.started_count}/{row.registered_count}
              </td>
              <td>{row.question_count}</td>
              <td style={{ textAlign: 'right', color: 'var(--text-muted)' }}>›</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
