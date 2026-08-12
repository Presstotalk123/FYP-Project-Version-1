export interface LoginActivitySummary {
  /** Consecutive calendar days (SGT) ending today with a login. 0 = no active streak. */
  current_streak: number;
  /** Year the active_dates belong to. */
  year: number;
  /** Month (1-12) the active_dates belong to. */
  month: number;
  /** Login dates within the requested month, as ISO `YYYY-MM-DD` strings. */
  active_dates: string[];
}

/** One calendar day's platform usage. `total_seconds` sums that day's sessions. */
export interface DailyUsage {
  /** Calendar day (SGT), ISO `YYYY-MM-DD`. */
  date: string;
  /** Sum of the day's login-session durations, in seconds. */
  total_seconds: number;
  /** Earliest login of the day (ISO datetime, UTC). */
  first_login_at: string;
  /** Latest recorded action of the day (ISO datetime, UTC). */
  last_action_at: string;
  /** Number of login sessions that day. */
  session_count: number;
}

/** A student's per-day usage for one month, plus the month total. */
export interface UsageSummary {
  year: number;
  month: number;
  /** Sum of `total_seconds` across the month's days. */
  total_seconds: number;
  days: DailyUsage[];
}

/** One student's month total, for the staff usage roster. */
export interface StudentUsageRow {
  student_id: number;
  name: string | null;
  email: string;
  class_group: string | null;
  total_seconds: number;
  /** Distinct calendar days with at least one session. */
  active_days: number;
}
