'use client';

import { useState } from 'react';
import {
  chatbotService,
  CounterexampleResponse,
  ContrastResponse,
} from '@/services/chatbot.service';

interface QueryReviewCardProps {
  query: string;
  isLoading: boolean;
  problemToken?: string;
  explanation?: string;
  hint?: string;
  dbStateIssue?: boolean;
  dbStateMessage?: string;
  /**
   * When provided, enables the lazy "Show me where this breaks" and "Compare
   * with a correct version" sections (SQL questions only). Omitted for labs.
   */
  questionId?: number;
}

/**
 * Splits a SQL string around the first case-insensitive occurrence of `token`.
 * Returns [before, matched, after] or null if not found.
 */
function splitOnToken(
  query: string,
  token: string
): [string, string, string] | null {
  if (!token) return null;
  const idx = query.toLowerCase().indexOf(token.toLowerCase());
  if (idx === -1) return null;
  return [
    query.slice(0, idx),
    query.slice(idx, idx + token.length),
    query.slice(idx + token.length),
  ];
}

/** Compact result table; optional `diff` highlights diverging rows. */
function MiniTable({
  columns,
  rows,
  diff,
}: {
  columns: string[];
  rows: unknown[][];
  diff?: boolean[];
}) {
  if (!columns.length) {
    return <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>No rows</p>;
  }
  return (
    <div className="table-wrap">
      <table className="da-table">
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={diff?.[i] ? { background: '#fef9c3' } : undefined}>
              {row.map((cell, j) => (
                <td key={j}>{cell === null || cell === undefined ? 'NULL' : String(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function QueryReviewCard({
  query,
  isLoading,
  problemToken = '',
  explanation = '',
  hint = '',
  dbStateIssue = false,
  dbStateMessage = '',
  questionId,
}: QueryReviewCardProps) {
  // ── Counterexample lazy-load state ────────────────────────────────────────
  const [ceStatus, setCeStatus] = useState<'idle' | 'loading' | 'done' | 'none' | 'error'>('idle');
  const [ceData, setCeData] = useState<CounterexampleResponse | null>(null);

  const loadCounterexample = async () => {
    if (questionId === undefined) return;
    setCeStatus('loading');
    try {
      const data = await chatbotService.getCounterexample(questionId, query);
      if (data.available) {
        setCeData(data);
        setCeStatus('done');
      } else {
        setCeStatus('none');
      }
    } catch {
      setCeStatus('error');
    }
  };

  // ── Contrast lazy-load state ──────────────────────────────────────────────
  const [ctStatus, setCtStatus] = useState<'idle' | 'loading' | 'done' | 'none' | 'error'>('idle');
  const [ctData, setCtData] = useState<ContrastResponse | null>(null);

  const loadContrast = async () => {
    if (questionId === undefined) return;
    setCtStatus('loading');
    try {
      const data = await chatbotService.getContrast(questionId, query);
      if (data.available) {
        setCtData(data);
        setCtStatus('done');
      } else {
        setCtStatus('none');
      }
    } catch {
      setCtStatus('error');
    }
  };

  // ── Loading skeleton ──────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="query-review-skeleton" style={{ marginTop: 12 }}>
        <div
          className="skeleton-block"
          style={{ height: 80, borderRadius: 8 }}
          aria-label="Loading AI review…"
        />
        <div className="skeleton-block" style={{ height: 64 }} />
      </div>
    );
  }

  // Nothing to show yet
  if (!explanation) return null;

  // ── Split query around problem token ─────────────────────────────────────
  const parts = splitOnToken(query, problemToken);

  return (
    <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>

      {/* DB state warning */}
      {dbStateIssue && dbStateMessage && (
        <div className="da-alert alert-warn" role="alert">
          <span>⚠️</span>
          <span>
            {dbStateMessage}{' '}
            Consider using the <strong>Reset Database</strong> button to restore
            your database.
          </span>
        </div>
      )}

      {/* SQL query with highlighted token */}
      <pre className="demo-code">
        <code>
          {parts ? (
            <>
              {parts[0]}
              <mark>{parts[1]}</mark>
              {parts[2]}
            </>
          ) : (
            query
          )}
        </code>
      </pre>

      {/* Review note */}
      <div className="sql-note">
        <h3>Review this part of your query</h3>
        <p>{explanation}</p>
        <p className="hint">💡 Hint: {hint}</p>
      </div>

      {/* ── Execution-grounded sections (SQL questions only) ── */}
      {questionId !== undefined && (
        <div style={{ display: 'grid', gap: 8 }}>

          {/* Counterexample: "Show me where this breaks" */}
          {ceStatus === 'idle' && (
            <button
              className="btn btn-ghost"
              style={{ justifySelf: 'start', fontSize: 12 }}
              onClick={loadCounterexample}
            >
              🔎 Show me where this breaks
            </button>
          )}

          {ceStatus === 'loading' && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
              Looking for a case that breaks your query…
            </p>
          )}

          {ceStatus === 'none' && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
              Couldn&apos;t construct a breaking case here — your query differs from the
              expected answer in another way. Check the hint above.
            </p>
          )}

          {ceStatus === 'error' && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
              Couldn&apos;t build a counterexample right now. Try again in a moment.
            </p>
          )}

          {ceStatus === 'done' && ceData && (
            <div className="sql-note" style={{ display: 'grid', gap: 10 }}>
              <h3>Watch what happens when I add this row</h3>
              <pre className="demo-code"><code>{ceData.injected_rows.join('\n')}</code></pre>
              <p style={{ margin: 0 }}>{ceData.explanation}</p>
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'grid', gap: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#b91c1c' }}>Your query now returns</span>
                  {ceData.student_result && (
                    <MiniTable columns={ceData.student_result.columns} rows={ceData.student_result.rows} />
                  )}
                </div>
                <div style={{ display: 'grid', gap: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#166534' }}>The expected answer returns</span>
                  {ceData.correct_result && (
                    <MiniTable columns={ceData.correct_result.columns} rows={ceData.correct_result.rows} />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Contrast: "Compare with a correct version" */}
          {ctStatus === 'idle' && (
            <button
              className="btn btn-ghost"
              style={{ justifySelf: 'start', fontSize: 12 }}
              onClick={loadContrast}
            >
              ⚖️ Compare with a correct version
            </button>
          )}

          {ctStatus === 'loading' && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
              Building a side-by-side comparison…
            </p>
          )}

          {(ctStatus === 'none' || ctStatus === 'error') && (
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
              Couldn&apos;t build a comparison right now. Try again in a moment.
            </p>
          )}

          {ctStatus === 'done' && ctData && (
            <div className="sql-note" style={{ display: 'grid', gap: 10 }}>
              <h3>The difference: {ctData.concept}</h3>
              <p style={{ margin: 0 }}>{ctData.explanation}</p>
              <div style={{ display: 'grid', gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#b91c1c' }}>Your version</span>
                <pre className="demo-code"><code>{ctData.your_query}</code></pre>
                {ctData.your_result && (
                  <MiniTable
                    columns={ctData.your_result.columns}
                    rows={ctData.your_result.rows}
                    diff={ctData.your_result.diff}
                  />
                )}
              </div>
              <div style={{ display: 'grid', gap: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#166534' }}>A correct version</span>
                <pre className="demo-code"><code>{ctData.corrected_query}</code></pre>
                {ctData.corrected_result && (
                  <MiniTable
                    columns={ctData.corrected_result.columns}
                    rows={ctData.corrected_result.rows}
                    diff={ctData.corrected_result.diff}
                  />
                )}
              </div>
              <p style={{ margin: 0, fontSize: 11, color: 'var(--text-muted)' }}>
                Highlighted rows differ between the two versions.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
