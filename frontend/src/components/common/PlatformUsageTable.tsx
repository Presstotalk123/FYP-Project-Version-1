'use client';

// Read-only daily platform-time table. Shows, per calendar day, the first login,
// the last recorded action, and the total time on the platform that day (the SUM
// of that day's login sessions — see backend app.services.platform_usage).
// Dependency-free and styled with the app's CSS tokens, to sit alongside
// LoginCalendar in the student dashboard popover and on the staff usage page.

import { DailyUsage } from '@/types/login-activity.types';
import { formatDuration } from '@/utils/format-duration';

const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

// login_date is an SGT civil date already ("YYYY-MM-DD") — format its parts
// directly (no timezone conversion, which could shift the day).
const formatDay = (isoDate: string): string => {
  const [, m, d] = isoDate.split('-').map(Number);
  return `${MONTH_ABBR[(m || 1) - 1]} ${d}`;
};

// Timestamps are stored UTC; the platform's civil timezone is Singapore, and the
// day grouping is SGT, so render clock times in SGT for consistency.
const formatTime = (isoDateTime: string): string =>
  new Date(isoDateTime).toLocaleTimeString('en-US', {
    timeZone: 'Asia/Singapore',
    hour: 'numeric',
    minute: '2-digit',
  });

interface PlatformUsageTableProps {
  days: DailyUsage[];
  totalSeconds: number;
  /** Dim the table while a new month is being fetched. */
  loading?: boolean;
}

export function PlatformUsageTable({ days, totalSeconds, loading }: PlatformUsageTableProps) {
  const cell: React.CSSProperties = { padding: '6px 8px', fontSize: 12, whiteSpace: 'nowrap' };
  const head: React.CSSProperties = {
    ...cell,
    textAlign: 'left',
    fontWeight: 700,
    color: 'var(--text-muted)',
    borderBottom: '1px solid var(--border)',
  };

  return (
    <div style={{ opacity: loading ? 0.55 : 1, transition: 'opacity 120ms ease' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8, gap: 16 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
          Time on platform
        </span>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-lilac)' }}>
          {formatDuration(totalSeconds)} this month
        </span>
      </div>

      {days.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '4px 0' }}>
          No activity recorded this month.
        </p>
      ) : (
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th style={head}>Date</th>
              <th style={head}>Login</th>
              <th style={head}>Last action</th>
              <th style={{ ...head, textAlign: 'right' }}>Time</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date}>
                <td style={{ ...cell, fontWeight: 600, color: 'var(--brand-charcoal)' }}>
                  {formatDay(d.date)}
                </td>
                <td style={{ ...cell, color: 'var(--text-muted)' }}>{formatTime(d.first_login_at)}</td>
                <td style={{ ...cell, color: 'var(--text-muted)' }}>{formatTime(d.last_action_at)}</td>
                <td style={{ ...cell, textAlign: 'right', fontWeight: 700, color: 'var(--brand-charcoal)' }}>
                  {formatDuration(d.total_seconds)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
