import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { Attempt, Progress } from '@/types/attempt.types';

export const attemptService = {
  async getQuestionAttempts(questionId: number): Promise<Attempt[]> {
    const response = await api.get<Attempt[]>(API_ENDPOINTS.ATTEMPTS.BY_QUESTION(questionId));
    return response.data;
  },

  async getProgress(): Promise<Progress[]> {
    const response = await api.get<Progress[]>(API_ENDPOINTS.ATTEMPTS.PROGRESS);
    return response.data;
  },
};
