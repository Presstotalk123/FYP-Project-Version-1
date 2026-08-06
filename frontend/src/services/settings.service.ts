import { API_ENDPOINTS } from '@/config/api.config';
import api from './api.service';

export interface ErdSettings {
  /** Students may author their own ERD questions. Off unless staff enable it. */
  student_authoring_enabled: boolean;
}

export const settingsService = {
  async getErdSettings(): Promise<ErdSettings> {
    const res = await api.get<ErdSettings>(API_ENDPOINTS.SETTINGS.ERD);
    return res.data;
  },

  async updateErdSettings(body: ErdSettings): Promise<ErdSettings> {
    const res = await api.put<ErdSettings>(API_ENDPOINTS.SETTINGS.ERD, body);
    return res.data;
  },
};
