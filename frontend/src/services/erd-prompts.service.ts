import { API_ENDPOINTS } from '@/config/api.config';
import api from './api.service';
import { ErdPromptListItem, ErdPromptVersionSummary } from '@/types/erd-prompts.types';

export const erdPromptsService = {
  async list(): Promise<ErdPromptListItem[]> {
    const res = await api.get<ErdPromptListItem[]>(API_ENDPOINTS.ERD_PROMPTS.LIST);
    return res.data;
  },

  async versions(key: string): Promise<ErdPromptVersionSummary[]> {
    const res = await api.get<ErdPromptVersionSummary[]>(API_ENDPOINTS.ERD_PROMPTS.VERSIONS(key));
    return res.data;
  },

  async save(key: string, content: string): Promise<ErdPromptVersionSummary> {
    const res = await api.put<ErdPromptVersionSummary>(API_ENDPOINTS.ERD_PROMPTS.DETAIL(key), { content });
    return res.data;
  },

  async activate(key: string, versionNo: number): Promise<ErdPromptVersionSummary> {
    const res = await api.post<ErdPromptVersionSummary>(API_ENDPOINTS.ERD_PROMPTS.ACTIVATE(key, versionNo));
    return res.data;
  },

  async resetToDefault(key: string): Promise<void> {
    await api.delete(API_ENDPOINTS.ERD_PROMPTS.OVERRIDE(key));
  },
};
