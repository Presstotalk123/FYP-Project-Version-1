import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { LoginActivitySummary } from '@/types/login-activity.types';

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
};
