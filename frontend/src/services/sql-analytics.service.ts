import api from "./api.service";
import { API_ENDPOINTS } from "@/config/api.config";
import type {
  SqlClassOverview,
  SqlEngagement,
  SqlQuestionAnalytics,
  SqlStudentDetail,
} from "@/types/sql-analytics.types";

export const sqlAnalyticsService = {
  async questionAnalytics(
    id: number,
    classGroup?: string,
  ): Promise<SqlQuestionAnalytics> {
    const r = await api.get<SqlQuestionAnalytics>(API_ENDPOINTS.SQL_ANALYTICS.QUESTION(id), {
      params: { ...(classGroup ? { class_group: classGroup } : {}) },
    });
    return r.data;
  },
  async studentDetail(questionId: number, studentId: number): Promise<SqlStudentDetail> {
    const r = await api.get<SqlStudentDetail>(
      API_ENDPOINTS.SQL_ANALYTICS.STUDENT(questionId, studentId),
    );
    return r.data;
  },
  async overview(classGroup?: string): Promise<SqlClassOverview> {
    const r = await api.get<SqlClassOverview>(API_ENDPOINTS.SQL_ANALYTICS.OVERVIEW, {
      params: { ...(classGroup ? { class_group: classGroup } : {}) },
    });
    return r.data;
  },
  async studentEngagement(classGroup?: string): Promise<SqlEngagement> {
    const r = await api.get<SqlEngagement>(API_ENDPOINTS.SQL_ANALYTICS.STUDENTS, {
      params: { ...(classGroup ? { class_group: classGroup } : {}) },
    });
    return r.data;
  },
  async classGroups(): Promise<string[]> {
    const r = await api.get<string[]>(API_ENDPOINTS.SQL_ANALYTICS.CLASS_GROUPS);
    return r.data;
  },
};
