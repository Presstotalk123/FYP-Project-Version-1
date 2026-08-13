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

/** A student's per-day usage for one month, plus the month and all-time totals. */
export interface UsageSummary {
  year: number;
  month: number;
  /** Sum of `total_seconds` across the month's days. */
  total_seconds: number;
  /** Sum of the student's session durations across all days. */
  all_time_seconds: number;
  /** Distinct calendar days with any session, all-time. */
  all_time_active_days: number;
  days: DailyUsage[];
}

/** One student's totals for the staff usage roster: selected month + all-time. */
export interface StudentUsageRow {
  student_id: number;
  name: string | null;
  email: string;
  class_group: string | null;
  /** Sum of the student's session durations in the selected month. */
  total_seconds: number;
  /** Distinct calendar days with a session in the selected month. */
  active_days: number;
  /** Sum of the student's session durations across all days. */
  all_time_seconds: number;
  /** Distinct calendar days with any session, all-time. */
  all_time_active_days: number;
}

/** Live count of users on the platform right now (staff dashboard card). */
export interface OnlineSummary {
  total: number;
  students: number;
  /** STAFF and ADMIN combined. */
  staff: number;
}

/** One currently-online user, for the card's expandable list. */
export interface OnlineUser {
  id: number;
  name: string | null;
  email: string;
  role: string;
  class_group: string | null;
  seconds_ago: number;
}
