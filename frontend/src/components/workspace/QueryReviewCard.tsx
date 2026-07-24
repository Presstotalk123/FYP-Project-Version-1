'use client';

import { QueryReviewResponse, LabQueryReviewResponse } from '@/services/chatbot.service';

interface QueryReviewCardProps {
  query: string;
  isLoading: boolean;
  problemToken?: string;
  explanation?: string;
  hint?: string;
  dbStateIssue?: boolean;
  dbStateMessage?: string;
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

export function QueryReviewCard({
  query,
  isLoading,
  problemToken = '',
  explanation = '',
  hint = '',
  dbStateIssue = false,
  dbStateMessage = '',
}: QueryReviewCardProps) {
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
    </div>
  );
}
