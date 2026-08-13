'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { loginActivityService } from '@/services/loginActivity.service';
import { queryKeys } from '@/services/query-keys';

// Matches the card's own poll cadence. The summary is ~40 bytes, so this stays
// cheap no matter how many students are online.
const POLL_MS = 60_000;

function lastSeen(secondsAgo: number): string {
  if (secondsAgo < 60) return 'just now';
  const minutes = Math.floor(secondsAgo / 60);
  return `${minutes}m ago`;
}

/**
 * How many people are using the platform right now, split by role, with an
 * expandable list of who.
 *
 * The list is a separate query enabled only once expanded, so the 60s poll
 * carries three integers whether five or five hundred students are online.
 */
export function ActiveUsersCard() {
  const [expanded, setExpanded] = useState(false);

  const summaryQuery = useQuery({
    queryKey: queryKeys.presenceSummary,
    queryFn: () => loginActivityService.getOnlineSummary(),
    // Override the app-wide staleTime: Infinity / no-refetch defaults in
    // providers.tsx — this is the one figure on the dashboard that must be live.
    staleTime: 0,
    refetchInterval: POLL_MS,
  });

  const onlineQuery = useQuery({
    queryKey: queryKeys.presenceOnline,
    queryFn: () => loginActivityService.getOnline(),
    enabled: expanded,
    staleTime: 0,
    refetchInterval: POLL_MS,
  });

  const summary = summaryQuery.data;

  return (
    <article className="card" style={{ marginBottom: 18 }}>
      <div className="metric">
        <div>
          <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Active Now
          </span>
          {summaryQuery.isError ? (
            <strong title="Could not load the active-user count">—</strong>
          ) : (
            <strong>{summary?.total ?? '—'}</strong>
          )}
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {summary
              ? `${summary.students} student${summary.students === 1 ? '' : 's'} · ${summary.staff} staff`
              : summaryQuery.isError
                ? 'Unavailable'
                : 'Loading…'}
          </span>
        </div>
        <span className="badge badge-success">Live</span>
      </div>

      {(summary?.total ?? 0) > 0 && (
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginTop: 12 }}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Hide' : 'Show more'}
        </button>
      )}

      {expanded && (
        <div style={{ marginTop: 12 }}>
          {onlineQuery.isLoading && <span style={{ color: 'var(--text-muted)' }}>Loading…</span>}
          {onlineQuery.isError && <span style={{ color: 'var(--text-muted)' }}>Could not load the list.</span>}
          {onlineQuery.data && (
            <ul className="presence-list">
              {onlineQuery.data.map((u) => (
                <li key={u.id}>
                  <span>{u.name || u.email}</span>
                  <span style={{ color: 'var(--text-muted)' }}>
                    {u.role}
                    {u.class_group ? ` · ${u.class_group}` : ''} · {lastSeen(u.seconds_ago)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}
