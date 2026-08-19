import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { Question, QuestionDetail, QuestionCount, Difficulty } from '@/types/question.types';

// The backend list endpoint caps `limit` at 500 (questions.py), so one request covers
// the whole bank today in a single round trip. Every caller of getQuestions() wants the
// full bank (Problems list, student practice, assessment picker, dashboard), so we still
// page through here — the loop is the size-independent safety net that keeps returning
// everything if the bank ever grows past PAGE_SIZE — mirroring the ER questions endpoint,
// which already returns its whole list unpaginated.
const PAGE_SIZE = 500;

export const questionService = {
  async getQuestions(params?: {
    difficulty?: Difficulty;
    search?: string;
  }): Promise<Question[]> {
    const all: Question[] = [];
    let skip = 0;
    // Loop until a short (or empty) page signals we've reached the end. Each page is
    // capped at PAGE_SIZE by the backend regardless of what we request.
    for (;;) {
      const response = await api.get<Question[]>(API_ENDPOINTS.QUESTIONS.BASE, {
        params: { ...params, skip, limit: PAGE_SIZE },
      });
      const page = response.data;
      all.push(...page);
      if (page.length < PAGE_SIZE) break;
      skip += PAGE_SIZE;
    }
    return all;
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
