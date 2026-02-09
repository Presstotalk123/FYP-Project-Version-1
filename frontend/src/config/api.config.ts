export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: '/auth/login',
    REGISTER: '/auth/register',
    ME: '/auth/me',
  },
  QUESTIONS: {
    BASE: '/questions',
    DETAIL: (id: number) => `/questions/${id}`,
  },
  EXECUTE: {
    BASE: '/execute',
  },
  ATTEMPTS: {
    BASE: '/attempts',
    HISTORY: '/attempts/history',
    PROGRESS: '/attempts/progress',
    BY_QUESTION: (id: number) => `/attempts/question/${id}`,
  },
};
