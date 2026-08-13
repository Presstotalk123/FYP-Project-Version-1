import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { StudentReportSummary, StudentFullReport } from '@/types/report.types';

export const reportService = {
  async getSummary(): Promise<StudentReportSummary> {
    const response = await api.get<StudentReportSummary>(API_ENDPOINTS.STUDENT_REPORT.SUMMARY);
    return response.data;
  },

  // Staff-only: a consolidated report (practice + per-assessment scores) for one student.
  async getForStudent(studentId: number): Promise<StudentFullReport> {
    const response = await api.get<StudentFullReport>(
      API_ENDPOINTS.STUDENT_REPORT.FOR_STUDENT(studentId),
    );
    return response.data;
  },
};
