import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { ExecuteRequest, ExecuteResponse } from '@/types/attempt.types';

export const executeService = {
  async executeQuery(request: ExecuteRequest): Promise<ExecuteResponse> {
    const response = await api.post<ExecuteResponse>(API_ENDPOINTS.EXECUTE.BASE, request);
    return response.data;
  },
};
