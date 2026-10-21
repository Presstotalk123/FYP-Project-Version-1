import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { LabLeaderboardResponse, OverallLeaderboardResponse } from '@/types/leaderboard.types';

export const leaderboardService = {
  /** Ranking of the students who have submitted to one lab. `classGroup` null = all groups. */
  async getLabLeaderboard(labId: number, classGroup: string | null): Promise<LabLeaderboardResponse> {
    const response = await api.get<LabLeaderboardResponse>(API_ENDPOINTS.LEADERBOARD.LAB(labId), {
      params: { class_group: classGroup ?? undefined },
    });
    return response.data;
  },

  /** Ranking of every student by SQL + ER + labs completed. `classGroup` null = all groups. */
  async getOverallLeaderboard(classGroup: string | null): Promise<OverallLeaderboardResponse> {
    const response = await api.get<OverallLeaderboardResponse>(API_ENDPOINTS.LEADERBOARD.OVERALL, {
      params: { class_group: classGroup ?? undefined },
    });
    return response.data;
  },
};
