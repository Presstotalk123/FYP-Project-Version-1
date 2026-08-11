import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { Question, QuestionDetail, QuestionCount, Difficulty } from '@/types/question.types';

export const questionService = {
  async getQuestions(params?: {
    difficulty?: Difficulty;
    search?: string;
  }): Promise<Question[]> {
    const response = await api.get<Question[]>(API_ENDPOINTS.QUESTIONS.BASE, { params });
    return response.data;
  },

  // Dashboard tile: backend-cached total + per-user attempted count (no full list fetch).
  async getCount(): Promise<QuestionCount> {
    const response = await api.get<QuestionCount>(API_ENDPOINTS.QUESTIONS.COUNT);
    return response.data;
  },

  async getQuestionById(id: number): Promise<QuestionDetail> {
    const response = await api.get<QuestionDetail>(API_ENDPOINTS.QUESTIONS.DETAIL(id));
    return response.data;
  },

  async publishQuestion(id: number): Promise<Question> {
    const response = await api.post<Question>(API_ENDPOINTS.QUESTIONS.PUBLISH(id));
    return response.data;
  },

  async unpublishQuestion(id: number): Promise<Question> {
    const response = await api.post<Question>(API_ENDPOINTS.QUESTIONS.UNPUBLISH(id));
    return response.data;
  },

  /** Soft delete, matching the backend's is_deleted flag. */
  async deleteQuestion(id: number): Promise<void> {
    await api.delete(API_ENDPOINTS.QUESTIONS.DETAIL(id));
  },
};
