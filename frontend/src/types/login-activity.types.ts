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
