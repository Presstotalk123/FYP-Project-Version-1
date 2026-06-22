import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import {
  Assessment,
  AssessmentDetail,
  AssessmentCreate,
  AssessmentUpdate,
  AssessmentStudentsResponse,
  StudentComponentScoresResponse,
} from '@/types/assessment.types';

export const assessmentService = {
  async createAssessment(data: AssessmentCreate): Promise<AssessmentDetail> {
    const response = await api.post(API_ENDPOINTS.ASSESSMENTS.BASE, data);
    return response.data;
  },

  async getAssessments(): Promise<Assessment[]> {
    const response = await api.get(API_ENDPOINTS.ASSESSMENTS.BASE);
    return response.data;
  },

  async getAssessmentById(id: number): Promise<AssessmentDetail> {
    const response = await api.get(API_ENDPOINTS.ASSESSMENTS.DETAIL(id));
    return response.data;
  },

  async updateAssessment(id: number, data: AssessmentUpdate): Promise<AssessmentDetail> {
    const response = await api.put(API_ENDPOINTS.ASSESSMENTS.DETAIL(id), data);
    return response.data;
  },

  async deleteAssessment(id: number): Promise<void> {
    await api.delete(API_ENDPOINTS.ASSESSMENTS.DETAIL(id));
  },

  async publishAssessment(id: number): Promise<Assessment> {
    const response = await api.post(API_ENDPOINTS.ASSESSMENTS.PUBLISH(id));
    return response.data;
  },

  async unpublishAssessment(id: number): Promise<Assessment> {
    const response = await api.post(API_ENDPOINTS.ASSESSMENTS.UNPUBLISH(id));
    return response.data;
  },

  async startAssessment(id: number): Promise<Assessment> {
    const response = await api.post(API_ENDPOINTS.ASSESSMENTS.START(id));
    return response.data;
  },

  async stopAssessment(id: number): Promise<Assessment> {
    const response = await api.post(API_ENDPOINTS.ASSESSMENTS.STOP(id));
    return response.data;
  },

  async getAssessmentStudents(id: number): Promise<AssessmentStudentsResponse> {
    const response = await api.get(API_ENDPOINTS.ASSESSMENTS.STUDENTS(id));
    return response.data;
  },

  async getStudentComponentScores(assessmentId: number, studentId: number): Promise<StudentComponentScoresResponse> {
    const response = await api.get(API_ENDPOINTS.ASSESSMENTS.STUDENT_SCORES(assessmentId, studentId));
    return response.data;
  },
};
