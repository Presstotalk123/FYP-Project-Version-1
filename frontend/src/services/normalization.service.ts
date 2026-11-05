import api from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import type { NormalizationAnalytics, NormalizationAttempt, NormalizationAuthoring, NormalizationPayload,
  NormalizationProgress, NormalizationQuestion, NormalizationQuestionInput } from '@/types/normalization.types';

const base = API_ENDPOINTS.NORMALIZATION.BASE;
export const normalizationService = {
  list: async () => (await api.get<NormalizationQuestion[]>(`${base}/questions`)).data,
  question: async (id: number) => (await api.get<NormalizationQuestion>(`${base}/questions/${id}`)).data,
  authoring: async (id: number) => (await api.get<NormalizationAuthoring>(`${base}/questions/${id}/authoring`)).data,
  progress: async () => (await api.get<NormalizationProgress[]>(`${base}/progress`)).data,
  history: async (id: number) => (await api.get<NormalizationAttempt[]>(`${base}/questions/${id}/submissions`)).data,
  attempt: async (id: string) => (await api.get<NormalizationAttempt>(`${base}/submissions/${id}`)).data,
  submit: async (id: number, payload: NormalizationPayload, preview = false) =>
    (await api.post<NormalizationAttempt>(`${base}/questions/${id}/${preview ? 'preview' : 'submissions'}`, payload)).data,
  save: async (input: NormalizationQuestionInput, id?: number) => id
    ? (await api.put<NormalizationAuthoring>(`${base}/questions/${id}`, input)).data
    : (await api.post<NormalizationAuthoring>(`${base}/questions`, input)).data,
  publish: async (id: number, published: boolean) =>
    (await api.post(`${base}/questions/${id}/${published ? 'publish' : 'unpublish'}`)).data,
  remove: async (id: number) => { await api.delete(`${base}/questions/${id}`); },
  capabilities: async () => (await api.get<{ semantic_judge_configured: boolean }>(`${base}/capabilities`)).data,
  analytics: async (id: number, classGroup = '') =>
    (await api.get<NormalizationAnalytics>(`${base}/questions/${id}/analytics`, { params: { class_group: classGroup || undefined } })).data,
  studentHistory: async (id: number, studentId: number) =>
    (await api.get<NormalizationAttempt[]>(`${base}/questions/${id}/students/${studentId}/submissions`)).data,
  requestReview: async (id: string, reason: string) =>
    (await api.post<NormalizationAttempt>(`${base}/submissions/${id}/review-request`, { reason })).data,
  review: async (id: string, decision: 'accepted' | 'rejected', reason: string, version: number) =>
    (await api.post<NormalizationAttempt>(`${base}/submissions/${id}/review`, { decision, reason, version })).data,
};

export function normalizationError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } }; message?: string })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? 'Invalid input').join('; ');
  return (error as Error)?.message || 'Unable to complete this action.';
}
