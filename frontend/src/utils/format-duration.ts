/**
 * Format a duration in seconds as a compact human string: `"1h 30m"`, `"45m"`,
 * `"2h"`, or `"0m"`. Used by the platform-time usage tables.
 *
 * Seconds are rounded to the nearest minute (the tracker's granularity is coarse
 * — see the ~60s heartbeat throttle — so sub-minute precision is noise).
 */
export function formatDuration(totalSeconds: number): string {
  const safe = Number.isFinite(totalSeconds) && totalSeconds > 0 ? totalSeconds : 0;
  const totalMinutes = Math.round(safe / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours === 0) return `${minutes}m`;
  if (minutes === 0) return `${hours}h`;
  return `${hours}h ${minutes}m`;
}
