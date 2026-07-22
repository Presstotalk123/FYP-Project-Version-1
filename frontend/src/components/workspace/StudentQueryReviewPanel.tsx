'use client';

import { LabQueryHistoryResponse } from '@/types/lab.types';

/* ── SVG icons ── */
const IconPlay = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="5 3 19 12 5 21 5 3"/>
  </svg>
);
const IconCheck = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);
const IconInfo = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>
);

interface StudentQueryReviewPanelProps {
  queries: LabQueryHistoryResponse[];
  currentIndex: number;
  executedIndices: Set<number>;
  onSelectQuery: (index: number) => void;
  onExecuteNext: () => void;
  isLoading: boolean;
  studentEmail: string;
}

export function StudentQueryReviewPanel({
  queries,
  currentIndex,
  executedIndices,
  onSelectQuery,
  onExecuteNext,
  isLoading,
  studentEmail,
}: StudentQueryReviewPanelProps) {
  if (isLoading) {
    return (
      <div className="loading-center" style={{ minHeight: 200 }}>
        <div className="spinner" style={{ width: 20, height: 20 }} />
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading student query history…</span>
      </div>
    );
  }

  if (queries.length === 0) {
    return (
      <div style={{ padding: 16 }}>
        <div className="da-alert alert-info">
          <strong>No History</strong>
          <span>This student has no query history for this lab.</span>
        </div>
      </div>
    );
  }

  const hasNextQuery = currentIndex < queries.length;

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: 12, gap: 10 }}>
      {/* Header card */}
      <div className="card" style={{ padding: 12, background: 'var(--surface-brand)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>Query History Review</span>
          <span className="badge brand-badge">{queries.length} queries total</span>
        </div>

        <button
          className="btn btn-brand"
          style={{ width: '100%', justifyContent: 'center', minHeight: 34, opacity: !hasNextQuery ? 0.5 : 1 }}
          onClick={onExecuteNext}
          disabled={!hasNextQuery}
        >
          <IconPlay />
          Execute Next Query ({currentIndex + 1}/{queries.length})
        </button>

        <div className="da-alert alert-info" style={{ marginTop: 8, fontSize: 12 }}>
          <strong style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <IconInfo /> Instructions
          </strong>
          <span>
            Queries are executed sequentially to recreate the student&apos;s database progression. Click a query to view it, or use &quot;Execute Next&quot; to step through chronologically.
          </span>
        </div>
      </div>

      {/* Query list */}
      <div style={{ flex: 1, overflow: 'auto', display: 'grid', gap: 8, alignContent: 'start' }}>
        {queries.map((query, index) => {
          const isExecuted = executedIndices.has(index);
          const isCurrent = index === currentIndex;
          const isPending = index > currentIndex;

          return (
            <div
              key={query.id}
              className="card"
              style={{
                padding: '10px 12px',
                cursor: 'pointer',
                borderColor: isCurrent ? 'var(--brand-lilac)' : undefined,
                borderWidth: isCurrent ? 2 : 1,
                opacity: isPending ? 0.6 : 1,
                transition: 'all 0.15s ease',
              }}
              onClick={() => onSelectQuery(index)}
            >
              {/* Badge row */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  <span className="badge neutral">#{index + 1}</span>
                  {isExecuted && <span className="badge badge-success"><IconCheck /> Reviewed</span>}
                  {isCurrent && !isExecuted && <span className="badge brand-badge">Current</span>}
                  {isPending && <span className="badge neutral">Pending</span>}
                </div>
                <span className={`badge ${query.success ? 'badge-success' : 'badge-danger'}`}>
                  {query.success ? 'Success' : 'Failed'}
                </span>
              </div>

              <p style={{ margin: '0 0 4px', fontSize: 11, color: 'var(--text-muted)' }}>
                {new Date(query.submitted_at).toLocaleString()}
              </p>

              <pre style={{
                margin: 0, fontSize: 11, lineHeight: 1.5, maxHeight: 100, overflow: 'auto',
                background: '#1e1e1e', color: '#d4d4d4',
                padding: '6px 8px', borderRadius: 'var(--radius)',
                fontFamily: 'var(--font-geist-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {query.query.length > 200 ? `${query.query.substring(0, 200)}...` : query.query}
              </pre>

              {!query.success && query.error_message && (
                <div className="da-alert alert-error" style={{ marginTop: 6, fontSize: 11 }}>
                  {query.error_message}
                </div>
              )}

              {query.success && (
                <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-muted)' }}>
                  {query.row_count} rows · {query.execution_time_ms.toFixed(2)}ms
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
