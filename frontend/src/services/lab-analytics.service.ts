import api from "./api.service";
import { API_ENDPOINTS } from "@/config/api.config";
import type { LabAnalytics, LabStudentDetail } from "@/types/lab-analytics.types";

export const labAnalyticsService = {
  async labAnalytics(id: number, classGroup?: string): Promise<LabAnalytics> {
    const r = await api.get<LabAnalytics>(API_ENDPOINTS.LAB_ANALYTICS.LAB(id), {
      params: { ...(classGroup ? { class_group: classGroup } : {}) },
    });
    return r.data;
  },
  async studentDetail(labId: number, studentId: number): Promise<LabStudentDetail> {
    const r = await api.get<LabStudentDetail>(
      API_ENDPOINTS.LAB_ANALYTICS.STUDENT(labId, studentId),
    );
    return r.data;
  },
};
