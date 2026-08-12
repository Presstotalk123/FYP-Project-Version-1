import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import {
  LoginActivitySummary,
  StudentUsageRow,
  UsageSummary,
} from '@/types/login-activity.types';

// Client-side throttle for the activity heartbeat. Meaningful actions fire far
// more often than we want to write (every API call + navigation), so we send at
// most one heartbeat per window; the backend throttles again as a backstop.
const HEARTBEAT_THROTTLE_MS = 60_000;
let lastHeartbeatAt = 0;
let heartbeatInFlight = false;

export const loginActivityService = {
  /**
   * Current login streak plus the active login days for a given month.
   * `year`/`month` are optional; the backend defaults to the current SGT month.
   */
  async getSummary(year?: number, month?: number): Promise<LoginActivitySummary> {
    const response = await api.get<LoginActivitySummary>(
      API_ENDPOINTS.LOGIN_ACTIVITY.SUMMARY,
      { params: { year, month } },
    );
    return response.data;
  },

  /**
   * Fire-and-forget activity ping that advances the current session's
   * last_action_at. Throttled client-side and best-effort — it never throws, so
   * callers (interceptor, navigation hook, chat) can call it freely. A no-op for
   * staff/admin server-side.
   */
  recordActivity(): void {
    const now = Date.now();
    if (heartbeatInFlight || now - lastHeartbeatAt < HEARTBEAT_THROTTLE_MS) return;
    if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) return;

    lastHeartbeatAt = now;
    heartbeatInFlight = true;
    api
      .post(API_ENDPOINTS.LOGIN_ACTIVITY.HEARTBEAT)
      .catch(() => {
        // Best-effort: allow a retry sooner if the ping failed.
        lastHeartbeatAt = 0;
      })
      .finally(() => {
        heartbeatInFlight = false;
      });
  },

  /** The caller's own daily platform-time usage for a month (self-serve). */
  async getUsage(year?: number, month?: number): Promise<UsageSummary> {
    const response = await api.get<UsageSummary>(API_ENDPOINTS.LOGIN_ACTIVITY.USAGE, {
      params: { year, month },
    });
    return response.data;
  },

  /** A given student's daily usage for a month. Staff/admin only. */
  async getStudentUsage(studentId: number, year?: number, month?: number): Promise<UsageSummary> {
    const response = await api.get<UsageSummary>(
      API_ENDPOINTS.LOGIN_ACTIVITY.STUDENT_USAGE(studentId),
      { params: { year, month } },
    );
    return response.data;
  },

  /** Per-student platform-time totals for a month, for the staff roster. */
  async getUsageOverview(year?: number, month?: number): Promise<StudentUsageRow[]> {
    const response = await api.get<StudentUsageRow[]>(
      API_ENDPOINTS.LOGIN_ACTIVITY.USAGE_OVERVIEW,
      { params: { year, month } },
    );
    return response.data;
  },
};
