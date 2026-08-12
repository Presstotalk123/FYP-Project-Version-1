'use client';

// Compact, read-only month calendar for the student dashboard's login-activity
// dropdown. Dependency-free (no @mantine/dates) and styled with the app's CSS
// tokens. Days on which the student logged in get a green filled circle; the
// current day gets a subtle ring. Prev/next chevrons ask the parent to load a
// different month via onNavigate — the parent owns which month is fetched so the
// active-days set always matches what is shown.

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

interface LoginCalendarProps {
  /** ISO `YYYY-MM-DD` strings for days with a login in the displayed month. */
  activeDates: Set<string>;
  /** Displayed year. */
  year: number;
  /** Displayed month, 1-12. */
  month: number;
  /** Requested when the user pages to another month. */
  onNavigate: (year: number, month: number) => void;
  /** Optional: dim the grid while the month is being fetched. */
  loading?: boolean;
}

const iso = (year: number, month: number, day: number): string =>
  `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

const ChevronLeft = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="15 18 9 12 15 6" />
  </svg>
);
const ChevronRight = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

export function LoginCalendar({ activeDates, year, month, onNavigate, loading }: LoginCalendarProps) {
  // Days in the month, and the weekday of the 1st normalised to Monday-first.
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstWeekday = (new Date(year, month - 1, 1).getDay() + 6) % 7; // 0 = Monday

  const today = new Date();
  const todayIso = iso(today.getFullYear(), today.getMonth() + 1, today.getDate());

  const goPrev = () => (month === 1 ? onNavigate(year - 1, 12) : onNavigate(year, month - 1));
  const goNext = () => (month === 12 ? onNavigate(year + 1, 1) : onNavigate(year, month + 1));

  // Leading blanks + day numbers, padded to whole weeks for a stable grid height.
  const cells: (number | null)[] = [
    ...Array<null>(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const navBtnStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 28, height: 28, border: '1px solid var(--border)', borderRadius: 'var(--radius)',
    background: 'transparent', color: 'var(--brand-charcoal)', cursor: 'pointer',
  };

  return (
    <div style={{ width: 252, opacity: loading ? 0.55 : 1, transition: 'opacity 120ms ease' }}>
      {/* Header: month/year with prev/next */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <button type="button" onClick={goPrev} style={navBtnStyle} aria-label="Previous month">
          <ChevronLeft />
        </button>
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
          {MONTH_NAMES[month - 1]} {year}
        </span>
        <button type="button" onClick={goNext} style={navBtnStyle} aria-label="Next month">
          <ChevronRight />
        </button>
      </div>

      {/* Weekday labels */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}>
        {WEEKDAYS.map((wd) => (
          <div key={wd} style={{ textAlign: 'center', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', padding: '2px 0' }}>
            {wd}
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2 }}>
        {cells.map((day, idx) => {
          if (day === null) return <div key={`b-${idx}`} />;
          const dateIso = iso(year, month, day);
          const active = activeDates.has(dateIso);
          const isToday = dateIso === todayIso;
          return (
            <div
              key={dateIso}
              title={active ? 'Logged in' : undefined}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                aspectRatio: '1 / 1', fontSize: 12,
                fontWeight: active ? 700 : 500,
                borderRadius: '50%',
                background: active ? 'var(--success)' : 'transparent',
                color: active ? '#fff' : 'var(--brand-charcoal)',
                boxShadow: !active && isToday ? 'inset 0 0 0 1.5px var(--brand-lilac)' : 'none',
              }}
            >
              {day}
            </div>
          );
        })}
      </div>
    </div>
  );
}
