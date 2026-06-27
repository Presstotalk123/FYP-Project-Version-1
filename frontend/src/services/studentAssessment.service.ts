import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import {
  StudentAssessmentListItem,
  StudentAssessmentDetail,
  AssessmentSessionResponse,
  ItemVisitResponse,
} from '@/types/assessment.types';

const E = API_ENDPOINTS.STUDENT_ASSESSMENTS;

export const studentAssessmentService = {
  async list(): Promise<StudentAssessmentListItem[]> {
    const response = await api.get(E.BASE);
    return response.data;
  },

  async getDetail(id: number): Promise<StudentAssessmentDetail> {
    const response = await api.get(E.DETAIL(id));
    return response.data;
  },

  async join(id: number, password?: string): Promise<AssessmentSessionResponse> {
    const response = await api.post(E.JOIN(id), password ? { password } : {});
    return response.data;
  },

  async getSession(id: number): Promise<AssessmentSessionResponse> {
    const response = await api.get(E.SESSION(id));
    return response.data;
  },

  async visitItem(assessmentId: number, itemId: number): Promise<ItemVisitResponse> {
    const response = await api.post(E.VISIT_ITEM(assessmentId, itemId));
    return response.data;
  },

  async submit(id: number): Promise<AssessmentSessionResponse> {
    const response = await api.post(E.SUBMIT(id));
    return response.data;
  },
};
