import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { Question, QuestionDetail, Difficulty } from '@/types/question.types';

export const questionService = {
  async getQuestions(params?: {
    difficulty?: Difficulty;
    search?: string;
  }): Promise<Question[]> {
    const response = await api.get<Question[]>(API_ENDPOINTS.QUESTIONS.BASE, { params });
    return response.data;
  },

  async getQuestionById(id: number): Promise<QuestionDetail> {
    const response = await api.get<QuestionDetail>(API_ENDPOINTS.QUESTIONS.DETAIL(id));
    return response.data;
  },
};
