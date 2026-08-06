// Centralized React Query keys so that data shared across staff pages is fetched
// once and cached under a single key (e.g. `questions` is used by both the
// Dashboard and the Problems page; `labs` by both Problems and Manage Labs).
// Keeping the keys here also makes post-mutation invalidation consistent.
export const queryKeys = {
  questions: ['questions'] as const,
  labs: ['labs'] as const,
  erdQuestions: ['erdQuestions'] as const,
  assessments: ['assessments'] as const,
  whitelist: ['whitelist'] as const,
  users: ['users'] as const,
  attempts: ['attempts'] as const,
  erdPrompts: ['erdPrompts'] as const,
  erdPromptVersions: (key: string) => ['erdPromptVersions', key] as const,

  // Student-scoped keys. SQL Questions and SQL Labs hit the same endpoints as the
  // staff pages (the backend role-filters), so students get their own keys to
  // avoid staff/student cache cross-contamination. `studentQuestions` encodes the
  // difficulty/search filters it is fetched with; invalidating by the
  // ['studentQuestions'] prefix clears every filter variant at once.
  studentQuestions: (params: { difficulty: string; search: string }) =>
    ['studentQuestions', params] as const,
  studentProgress: ['studentProgress'] as const,
  studentLabs: ['studentLabs'] as const,
  studentAssessments: ['studentAssessments'] as const,

  // Static per-resource content, cached so switching between assessment items
  // (a full route remount) does not re-download the prompt/schema/task list.
  // Keyed by resource id; dynamic state (attempts, sessions, conversation) is
  // deliberately NOT cached and keeps fetching live.
  questionById: (id: number) => ['questionById', id] as const,
  erQuestionById: (id: number) => ['erQuestionById', id] as const,
  labTasks: (id: number) => ['labTasks', id] as const,
};
