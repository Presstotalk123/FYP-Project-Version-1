// Centralized React Query keys so that data shared across staff pages is fetched
// once and cached under a single key (e.g. `questions` is used by both the
// Dashboard and the Problems page; `labs` by both Problems and Manage Labs).
// Keeping the keys here also makes post-mutation invalidation consistent.
export const queryKeys = {
  questions: ['questions'] as const,
  labs: ['labs'] as const,
  erdQuestions: ['erdQuestions'] as const,
  assessments: ['assessments'] as const,
  // Admin dashboard: one row per assessment, plus platform registered/signed-in counts.
  // Shared by the Overview and Assessments tabs so it is fetched once.
  assessmentAnalyticsSummary: ['assessmentAnalyticsSummary'] as const,
  // Per-assessment item analytics, keyed by class group so the cohort view and each
  // tutorial group are cached separately — re-picking a group costs no request.
  assessmentItemAnalytics: (assessmentId: number, classGroup: string | null) =>
    ['assessmentItemAnalytics', assessmentId, classGroup] as const,
  // Per-question student drill-down, keyed by question and class group so each expansion
  // caches separately and collapsing then re-expanding costs no request.
  assessmentItemStudents: (assessmentId: number, itemId: number, classGroup: string | null) =>
    ['assessmentItemStudents', assessmentId, itemId, classGroup] as const,
  whitelist: ['whitelist'] as const,
  users: ['users'] as const,
  attempts: ['attempts'] as const,
  erdPrompts: ['erdPrompts'] as const,
  erdPromptVersions: (key: string) => ['erdPromptVersions', key] as const,
  // The staff-tunable ERD toggle. Reads are open to any authenticated user, so
  // this is shared by the staff settings page and the student question list.
  erdSettings: ['erdSettings'] as const,

  // Student-scoped keys. SQL Questions and SQL Labs hit the same endpoints as the
  // staff pages (the backend role-filters), so students get their own keys to
  // avoid staff/student cache cross-contamination. `studentQuestions` encodes the
  // difficulty/search filters it is fetched with; invalidating by the
  // ['studentQuestions'] prefix clears every filter variant at once.
  studentQuestions: (params: { difficulty: string; search: string }) =>
    ['studentQuestions', params] as const,
  studentProgress: ['studentProgress'] as const,
  // ERD's counterpart to studentProgress: per-question completion for the list.
  studentErdProgress: ['studentErdProgress'] as const,
  // Course syllabus — shared by the student Course Info page and the staff editor
  // (same content). Invalidated after a staff save so the student page refetches.
  courseInfo: ['courseInfo'] as const,
  studentLabs: ['studentLabs'] as const,
  studentAssessments: ['studentAssessments'] as const,
  // Practice-completion counts for the student Report page.
  studentReportSummary: ['studentReportSummary'] as const,
  // Staff per-student full report (practice + per-assessment scores), keyed by student.
  studentFullReport: (studentId: number) => ['studentFullReport', studentId] as const,
  // Dashboard tiles: lightweight {total, attempted} counts (backend-cached totals).
  studentQuestionCount: ['studentQuestionCount'] as const,
  studentErdCount: ['studentErdCount'] as const,
  // Login streak + a month's active login days for the dashboard calendar.
  // Keyed by year/month so navigating the calendar caches each month separately.
  studentLoginActivity: (year: number, month: number) =>
    ['studentLoginActivity', year, month] as const,
  // Platform-time usage. The student's own per-day usage for a month; the staff
  // roster of per-student totals; one student's per-day usage (staff drill-down).
  // All keyed by year/month so each month caches separately.
  studentUsage: (year: number, month: number) =>
    ['studentUsage', year, month] as const,
  usageOverview: (year: number, month: number) =>
    ['usageOverview', year, month] as const,
  studentUsageByStaff: (studentId: number, year: number, month: number) =>
    ['studentUsageByStaff', studentId, year, month] as const,

  // Static per-resource content, cached so switching between assessment items
  // (a full route remount) does not re-download the prompt/schema/task list.
  // Keyed by resource id; dynamic state (attempts, sessions, conversation) is
  // deliberately NOT cached and keeps fetching live.
  questionById: (id: number) => ['questionById', id] as const,
  erQuestionById: (id: number) => ['erQuestionById', id] as const,
  labTasks: (id: number) => ['labTasks', id] as const,

  // Live presence for the /admin active-user card. Unlike everything else here
  // these poll (see ActiveUsersCard) — they are the one genuinely live figure
  // on the dashboard, so they override the global staleTime: Infinity.
  presenceSummary: ['presenceSummary'] as const,
  presenceOnline: ['presenceOnline'] as const,

  // Learning Analytics Dashboard (student-scoped).
  ladConceptGraph: ['ladConceptGraph'] as const,
  ladPeerBenchmark: ['ladPeerBenchmark'] as const,
  // Concept taxonomy (shared) + a question's tags (staff editor).
  ladConcepts: ['ladConcepts'] as const,
  ladQuestionConcepts: (questionId: number) => ['ladQuestionConcepts', questionId] as const,
};
