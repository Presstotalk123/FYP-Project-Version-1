export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== 'undefined' && window.location.hostname === 'proud-stone-0ec93a000.2.azurestaticapps.net'
    ? 'https://aidb-backend.azurewebsites.net/api/v1'
    : 'http://localhost:8000/api/v1');

export const API_ENDPOINTS = {
  AUTH: {
    GOOGLE: '/auth/google',
    ME: '/auth/me',
  },
  QUESTIONS: {
    BASE: '/questions',
    DETAIL: (id: number) => `/questions/${id}`,
  },
  PROBLEMS: {
    BASE: '/problems',
  },
  SQL_LAB_QUESTIONS: {
    BASE: '/sql-lab-questions',
    DETAIL: (id: number) => `/sql-lab-questions/${id}`,
    RUN: (id: number) => `/sql-lab-questions/${id}/run`,
    SUBMIT: (id: number) => `/sql-lab-questions/${id}/submit`,
    DATABASE: (id: number) => `/sql-lab-questions/${id}/database`,
    RESET: (id: number) => `/sql-lab-questions/${id}/reset`,
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
    LAB_HISTORY: (labId: number) => `/labs/${labId}/history`,
    ALL_HISTORY: '/labs/history',
    PREVIEW: (id: number) => `/labs/${id}/preview/schema`,
    TASKS: (labId: number) => `/labs/${labId}/tasks`,
    TASK_DETAIL: (labId: number, taskId: number) => `/labs/${labId}/tasks/${taskId}`,
    TASK_ASSIGN: (labId: number, taskId: number) => `/labs/${labId}/tasks/${taskId}/assign`,
    TASK_VALIDATE: '/labs/tasks/validate',
    TASK_SUBMIT: '/labs/tasks/submit',
    TASK_PROGRESS: (labId: number) => `/labs/${labId}/progress`,
    STUDENT_ATTEMPTS: (labId: number) => `/labs/${labId}/student-attempts`,
    STUDENT_QUERY_HISTORY: (labId: number, studentId: number) => `/labs/${labId}/students/${studentId}/history`,
  },
  UNIFIED_LABS: {
    BASE: '/labs',
    DETAIL: (id: number) => `/labs/${id}`,
    ITEMS: (id: number) => `/labs/${id}/items`,
    ITEM: (id: number, itemId: number) => `/labs/${id}/items/${itemId}`,
    ITEMS_ORDER: (id: number) => `/labs/${id}/items/order`,
    SESSION_START: (id: number) => `/labs/${id}/session/start`,
    ITEM_SUBMIT: (id: number, itemId: number) => `/labs/${id}/items/${itemId}/submit`,
    ITEM_SUBMISSION: (id: number, itemId: number) => `/labs/${id}/items/${itemId}/submission`,
    ITEM_RUN: (id: number, itemId: number) => `/labs/${id}/items/${itemId}/run`,
    ITEM_DATABASE: (id: number, itemId: number) => `/labs/${id}/items/${itemId}/database`,
    ITEM_RESET: (id: number, itemId: number) => `/labs/${id}/items/${itemId}/reset`,
    PROGRESS: (id: number) => `/labs/${id}/item-progress`,
    PUBLISH: (id: number) => `/labs/${id}/publish`,
    UNPUBLISH: (id: number) => `/labs/${id}/unpublish`,
    START: (id: number) => `/labs/${id}/start`,
    STOP: (id: number) => `/labs/${id}/stop`,
    OVERRIDE: (subId: number) => `/labs/submissions/${subId}/override`,
    STUDENTS: (id: number) => `/labs/${id}/students`,
    SUBMISSIONS: (id: number) => `/labs/${id}/submissions`,
  },
};