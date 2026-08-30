export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== 'undefined' && window.location.hostname === 'zealous-stone-03626e900.7.azurestaticapps.net'
    ? 'https://ntu-akela-backend-ggcpejb0evb3fbg5.southeastasia-01.azurewebsites.net/api/v1'
    : 'http://localhost:8000/api/v1');

export const API_ENDPOINTS = {
  AUTH: {
    GOOGLE: '/auth/google',
    MICROSOFT: '/auth/microsoft',
    /** Local development only — the backend 404s this unless DEV_LOGIN_ENABLED. */
    DEV_LOGIN: '/auth/dev-login',
    ME: '/auth/me',
  },
  LOGIN_ACTIVITY: {
    SUMMARY: '/login-activity',
    HEARTBEAT: '/login-activity/heartbeat',
    LEAVE: '/login-activity/leave',
    ONLINE_SUMMARY: '/login-activity/online-summary',
    ONLINE: '/login-activity/online',
    USAGE: '/login-activity/usage',
    STUDENT_USAGE: (studentId: number) => `/login-activity/students/${studentId}/usage`,
    USAGE_OVERVIEW: '/login-activity/usage-overview',
  },
  QUESTIONS: {
    BASE: '/questions',
    COUNT: '/questions/count',
    DETAIL: (id: number) => `/questions/${id}`,
    PUBLISH: (id: number) => `/questions/${id}/publish`,
    UNPUBLISH: (id: number) => `/questions/${id}/unpublish`,
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
    QUESTIONS_COUNT: '/er-diagram/questions/count',
    PROGRESS: '/er-diagram/progress',
    QUESTION_DETAIL: (id: number) => `/er-diagram/questions/${id}`,
    QUESTION_MODEL_ANSWER: (id: number) => `/er-diagram/questions/${id}/model-answer`,
    QUESTION_PUBLISH: (id: number) => `/er-diagram/questions/${id}/publish`,
    QUESTION_UNPUBLISH: (id: number) => `/er-diagram/questions/${id}/unpublish`,
    SUBMISSION: '/er-diagram/submission',
    CONVERSATION: '/er-diagram/conversation',
    DRAFT: '/er-diagram/draft',
  },
  ER_ANALYTICS: {
    QUESTION: (id: number) => `/er-diagram/questions/${id}/analytics`,
    STUDENT: (id: number, studentId: number) =>
      `/er-diagram/questions/${id}/students/${studentId}/submissions`,
    SUBMISSION: (submissionId: number) => `/er-diagram/submissions/${submissionId}`,
    SUBMISSION_SCORE: (submissionId: number) => `/er-diagram/submissions/${submissionId}/score`,
    SUBMISSION_IMAGE: (submissionId: number) =>
      `/er-diagram/submissions/${submissionId}/image`,
    OVERVIEW: '/er-diagram/analytics/overview',
    /** Per-student engagement across every ERD question (admin ERD tab). */
    STUDENTS: '/er-diagram/analytics/students',
    CLASS_GROUPS: '/er-diagram/analytics/class-groups',
    /** A student's autosaved canvas, read as staff. */
    STUDENT_DRAFT: (id: number, studentId: number) =>
      `/er-diagram/questions/${id}/students/${studentId}/draft`,
    /** Staff create a submission for a student who never submitted one. */
    ADD_STUDENT_SUBMISSION: (id: number, studentId: number) =>
      `/er-diagram/questions/${id}/students/${studentId}/submission`,
    /** Regrade every stored submission against the current rubric. */
    REGRADE: (id: number) => `/er-diagram/questions/${id}/regrade`,
    REGRADE_STATUS: (id: number) => `/er-diagram/questions/${id}/regrade/status`,
  },
  SQL_ANALYTICS: {
    QUESTION: (id: number) => `/questions/${id}/analytics`,
    STUDENT: (id: number, studentId: number) =>
      `/questions/${id}/students/${studentId}/detail`,
  },
  LAB_ANALYTICS: {
    LAB: (id: number) => `/labs/${id}/analytics`,
    STUDENT: (id: number, studentId: number) =>
      `/labs/${id}/students/${studentId}/detail`,
  },
  SETTINGS: {
    ERD: '/settings/erd',
  },
  COURSE_INFO: {
    BASE: '/course-info',
  },
  ERD_PROMPTS: {
    LIST: '/erd-prompts',
    DETAIL: (key: string) => `/erd-prompts/${key}`,
    VERSIONS: (key: string) => `/erd-prompts/${key}/versions`,
    ACTIVATE: (key: string, versionNo: number) => `/erd-prompts/${key}/versions/${versionNo}/activate`,
    OVERRIDE: (key: string) => `/erd-prompts/${key}/override`,
  },
  CHATBOT: {
    SEND: '/chatbot/send',
    QUERY_REVIEW: '/chatbot/query-review',
    COUNTEREXAMPLE: '/chatbot/counterexample',
    CONTRAST: '/chatbot/contrast',
    WORKED_EXAMPLE: '/chatbot/worked-example',
    LAB_CHAT: '/chatbot/lab-chat',
    LAB_QUERY_REVIEW: '/chatbot/lab-query-review',
    COURSE_CHAT: '/chatbot/course-chat',
    CONVERSATION: '/chatbot/conversation',
    LAB_CONVERSATION: '/chatbot/lab-conversation',
  },
  LABS: {
    BASE: '/labs',
    DETAIL: (id: number) => `/labs/${id}`,
    PUBLISH: (id: number) => `/labs/${id}/publish`,
    UNPUBLISH: (id: number) => `/labs/${id}/unpublish`,
    HIDE_RESULTS: (id: number) => `/labs/${id}/hide-results`,
    SHOW_RESULTS: (id: number) => `/labs/${id}/show-results`,
    DISABLE_AI_ASSIST: (id: number) => `/labs/${id}/disable-ai-assist`,
    ENABLE_AI_ASSIST: (id: number) => `/labs/${id}/enable-ai-assist`,
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
  ASSESSMENTS: {
    BASE: '/assessments',
    DETAIL: (id: number) => `/assessments/${id}`,
    PUBLISH: (id: number) => `/assessments/${id}/publish`,
    UNPUBLISH: (id: number) => `/assessments/${id}/unpublish`,
    START: (id: number) => `/assessments/${id}/start`,
    STOP: (id: number) => `/assessments/${id}/stop`,
    STUDENTS: (id: number) => `/assessments/${id}/students`,
    STUDENT_SCORES: (id: number, studentId: number) => `/assessments/${id}/students/${studentId}/component-scores`,
    ITEM_ANALYTICS: (id: number) => `/assessments/${id}/item-analytics`,
    ANALYTICS_SUMMARY: '/assessments/analytics/summary',
    ITEM_STUDENTS: (id: number, itemId: number) =>
      `/assessments/${id}/items/${itemId}/students`,
    RESET_STUDENT: (id: number, studentId: number) => `/assessments/${id}/students/${studentId}/reset`,
    WINDOWS: (id: number) => `/assessments/${id}/windows`,
    CLASS_GROUPS: (id: number) => `/assessments/${id}/class-groups`,
    CLASS_GROUPS_ALL: '/assessments/class-groups',
  },
  STUDENT_REPORT: {
    SUMMARY: '/student-report/summary',
    FOR_STUDENT: (studentId: number) => `/student-report/students/${studentId}`,
  },
  LAD: {
    CONCEPT_GRAPH: '/lad/concept-graph',
    PEER_BENCHMARK: '/lad/peer-benchmark',
    SCAFFOLDING: (questionId: number) => `/lad/scaffolding/${questionId}`,
    CONCEPTS: '/lad/concepts',
    QUESTION_CONCEPTS: (questionId: number) => `/lad/questions/${questionId}/concepts`,
  },
  STUDENT_ASSESSMENTS: {
    BASE: '/student-assessments',
    DETAIL: (id: number) => `/student-assessments/${id}`,
    JOIN: (id: number) => `/student-assessments/${id}/join`,
    SESSION: (id: number) => `/student-assessments/${id}/session`,
    VISIT_ITEM: (id: number, itemId: number) => `/student-assessments/${id}/session/visit-item/${itemId}`,
    SUBMIT: (id: number) => `/student-assessments/${id}/session/submit`,
  },
};