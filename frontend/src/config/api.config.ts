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
  ER_DIAGRAM: {
    GENERATE_RUBRIC: '/er-diagram/rubric/generate',
    QUESTIONS: '/er-diagram/questions',
    QUESTION_DETAIL: (id: number) => `/er-diagram/questions/${id}`,
    SUBMISSION: '/er-diagram/submission',
  },
  CHATBOT: {
    SEND: '/chatbot/send',
  },
  LABS: {
    BASE: '/labs',
    DETAIL: (id: number) => `/labs/${id}`,
    PUBLISH: (id: number) => `/labs/${id}/publish`,
    UNPUBLISH: (id: number) => `/labs/${id}/unpublish`,
    START: (id: number) => `/labs/${id}/start`,
    STOP: (id: number) => `/labs/${id}/stop`,
    SESSION_START: (id: number) => `/labs/${id}/session/start`,
    SESSION_GET: (id: number) => `/labs/${id}/session`,
    SESSION_EXECUTE: (sessionId: number) => `/labs/session/${sessionId}/execute`,
    SESSION_ATTEMPTS: (sessionId: number) => `/labs/session/${sessionId}/attempts`,
    SESSION_DATABASE: (sessionId: number) => `/labs/session/${sessionId}/database`,
    SESSION_RESET: (id: number) => `/labs/${id}/session/reset`,
    SESSION_EXIT: (id: number) => `/labs/${id}/session/exit`,
    PREVIEW: (id: number) => `/labs/${id}/preview/schema`,
  },
};