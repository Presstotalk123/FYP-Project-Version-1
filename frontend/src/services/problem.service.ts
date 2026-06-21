import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { ProblemListResponse, ProblemQueryParams } from '@/types/problem.types';

export const problemService = {
  async getProblems(params?: ProblemQueryParams): Promise<ProblemListResponse> {
    const response = await api.get<ProblemListResponse>(API_ENDPOINTS.PROBLEMS.BASE, { params });
    return response.data;
  },
};
