import api from '@/services/api.service';
import {
  RaAttempt, RaCheckpoint, RaCheckResponse, RaExample, RaExampleDataResponse, RaNotationResponse, RaPlaygroundGradeResponse,
  RaPlaygroundRunResponse, RaQuestion, RaPartInput, RaQuestionInput, RaQuestionListItem, RaQuestionStaff,
  RaSchemaTextResponse, RaStatus, RaSubmitResponse, RaValidateResponse, RaClassAnalytics, RaQuestionAnalytics,
  RaStudentAttempts, RaAnswerFormat, RaFormatConvertResponse, RaStepSpecStaff, RaTryStepsResponse, RaRegradePreview,
} from '@/types/ra.types';

/** RA endpoints, relative to the shared API base URL (…/api/v1). */
export const RA_ENDPOINTS = {
  STATUS: '/ra/status',
  PLAYGROUND_EXAMPLES: '/ra/playground/examples',
  PLAYGROUND_RUN: '/ra/playground/run',
  PLAYGROUND_GRADE: '/ra/playground/grade',
  NOTATION: '/ra/notation',
  ANALYTICS: '/ra/analytics',
  QUESTIONS: '/ra/questions',
  QUESTIONS_VALIDATE: '/ra/questions/validate',
  QUESTIONS_SCHEMA_FROM_TEXT: '/ra/questions/schema-from-text',
  QUESTIONS_EXAMPLE_DATA: '/ra/questions/example-data',
  QUESTIONS_CONVERT_FORMAT: '/ra/questions/convert-format',
  QUESTIONS_TRY_STEPS: '/ra/questions/try-steps',
  QUESTION: (id: number) => `/ra/questions/${id}`,
  QUESTION_EDIT: (id: number) => `/ra/questions/${id}/edit`,
  QUESTION_CHECK: (id: number) => `/ra/questions/${id}/check`,
  QUESTION_SUBMIT: (id: number) => `/ra/questions/${id}/submit`,
  QUESTION_ATTEMPTS: (id: number) => `/ra/questions/${id}/attempts`,
};

export const raQueryKeys = {
  status: ['ra', 'status'] as const,
  playgroundExamples: ['ra', 'playground', 'examples'] as const,
  questions: ['ra', 'questions'] as const,
  question: (id: number) => ['ra', 'questions', id] as const,
  questionEdit: (id: number) => ['ra', 'questions', id, 'edit'] as const,
  attempts: (id: number) => ['ra', 'questions', id, 'attempts'] as const,
  classAnalytics: (group: string) => ['ra', 'analytics', 'class', group] as const,
  classGroups: ['ra', 'analytics', 'class-groups'] as const,
  questionAnalytics: (id: number, group: string) => ['ra', 'analytics', 'questions', id, group] as const,
  studentAttempts: (id: number, studentId: number) => ['ra', 'analytics', 'questions', id, 'students', studentId] as const,
};

export const raService = {
  /** Whether the RA module is switched on (RA_ENABLED). Treats any failure as "off". */
  async getStatus(): Promise<RaStatus> {
    try {
      const response = await api.get<RaStatus>(RA_ENDPOINTS.STATUS);
      return response.data;
    } catch {
      return { enabled: false, aggregate_nulls: 'sql' };
    }
  },

  async getPlaygroundExamples(): Promise<RaExample[]> {
    const response = await api.get<RaExample[]>(RA_ENDPOINTS.PLAYGROUND_EXAMPLES);
    return response.data;
  },

  /** Load the schema (and data), then evaluate `expression` if given. Nothing is saved. */
  async runPlayground(schemaSql: string, dataSql: string, expression: string): Promise<RaPlaygroundRunResponse> {
    const response = await api.post<RaPlaygroundRunResponse>(RA_ENDPOINTS.PLAYGROUND_RUN, {
      schema_sql: schemaSql,
      data_sql: dataSql,
      expression,
    });
    return response.data;
  },

  /** Grade `answer` against `modelAnswer` on this schema. Nothing is saved. The staff
   *  form's test bench passes the question's checkpoints and set/bag choice too. */
  async gradePlayground(schemaSql: string, dataSql: string, modelAnswer: string, answer: string,
    options: { checkpoints?: RaCheckpoint[] | null; compareBags?: boolean } = {}): Promise<RaPlaygroundGradeResponse> {
    const response = await api.post<RaPlaygroundGradeResponse>(RA_ENDPOINTS.PLAYGROUND_GRADE, {
      schema_sql: schemaSql,
      data_sql: dataSql,
      model_answer: modelAnswer,
      answer,
      checkpoints: options.checkpoints ?? null,
      compare_bags: options.compareBags ?? false,
    });
    return response.data;
  },

  async listQuestions(): Promise<RaQuestionListItem[]> {
    return (await api.get<RaQuestionListItem[]>(RA_ENDPOINTS.QUESTIONS)).data;
  },

  async getQuestion(id: number): Promise<RaQuestion> {
    return (await api.get<RaQuestion>(RA_ENDPOINTS.QUESTION(id))).data;
  },

  /** Staff only: everything, including the model answer. */
  async getQuestionForEdit(id: number): Promise<RaQuestionStaff> {
    return (await api.get<RaQuestionStaff>(RA_ENDPOINTS.QUESTION_EDIT(id))).data;
  },

  /** Staff only: check one part's model answer and preview its test databases; nothing is saved. */
  async validateQuestion(input: Pick<RaQuestionInput, 'schema_sql' | 'data_sql' | 'compare_bags' | 'example_data_sql'>
    & Pick<RaPartInput, 'model_answer' | 'checkpoints'>
    & { answer_format?: RaAnswerFormat; steps?: RaStepSpecStaff[] | null }): Promise<RaValidateResponse> {
    return (await api.post<RaValidateResponse>(RA_ENDPOINTS.QUESTIONS_VALIDATE, input)).data;
  },

  /** The answer in textbook notation (σ with its condition as a subscript …), for the editor's preview. */
  async notation(program: string, names: string[] = []): Promise<RaNotationResponse> {
    return (await api.post<RaNotationResponse>(RA_ENDPOINTS.NOTATION, { program, names })).data;
  },

  // ── staff analytics (empty class group = every class) ──
  async classAnalytics(classGroup: string): Promise<RaClassAnalytics> {
    return (await api.get<RaClassAnalytics>(`${RA_ENDPOINTS.ANALYTICS}/class`,
      { params: classGroup ? { class_group: classGroup } : {} })).data;
  },

  async classGroups(): Promise<string[]> {
    return (await api.get<string[]>(`${RA_ENDPOINTS.ANALYTICS}/class-groups`)).data;
  },

  async questionAnalytics(id: number, classGroup: string): Promise<RaQuestionAnalytics> {
    return (await api.get<RaQuestionAnalytics>(`${RA_ENDPOINTS.ANALYTICS}/questions/${id}`,
      { params: classGroup ? { class_group: classGroup } : {} })).data;
  },

  async studentAttempts(id: number, studentId: number): Promise<RaStudentAttempts> {
    return (await api.get<RaStudentAttempts>(`${RA_ENDPOINTS.ANALYTICS}/questions/${id}/students/${studentId}`)).data;
  },

  /** The next batch of past attempts the current grader would change (nothing is saved). */
  async regradePreview(id: number, afterId: number | null): Promise<RaRegradePreview> {
    return (await api.post<RaRegradePreview>(`${RA_ENDPOINTS.ANALYTICS}/questions/${id}/regrade/preview`,
      { after_id: afterId })).data;
  },

  /** Regrade and save these attempts; staff overrides are kept. */
  async regradeApply(id: number, attemptIds: number[]): Promise<{ changed: number }> {
    return (await api.post<{ changed: number }>(`${RA_ENDPOINTS.ANALYTICS}/questions/${id}/regrade/apply`,
      { attempt_ids: attemptIds })).data;
  },

  /** Staff only: turn a schema written as text (``STUDENT(*Sid, Sname)``) into CREATE TABLE statements. */
  async schemaFromText(text: string, linkKeys: boolean): Promise<RaSchemaTextResponse> {
    return (await api.post<RaSchemaTextResponse>(RA_ENDPOINTS.QUESTIONS_SCHEMA_FROM_TEXT,
      { text, link_keys: linkKeys })).data;
  },

  /**
   * Staff only: example data for a question whose INSERT box is empty — ``current`` as it is
   * if the schema still accepts it, else built from the schema and model answers;
   * ``variant`` > 0 gives another one (Regenerate).
   */
  async exampleData(schemaSql: string, modelAnswers: string[], variant = 0,
    current: string | null = null): Promise<RaExampleDataResponse> {
    return (await api.post<RaExampleDataResponse>(RA_ENDPOINTS.QUESTIONS_EXAMPLE_DATA,
      { schema_sql: schemaSql, model_answers: modelAnswers, variant, current })).data;
  },

  async createQuestion(input: RaQuestionInput): Promise<RaQuestionStaff> {
    return (await api.post<RaQuestionStaff>(RA_ENDPOINTS.QUESTIONS, input)).data;
  },

  async updateQuestion(id: number, input: RaQuestionInput): Promise<RaQuestionStaff> {
    return (await api.put<RaQuestionStaff>(RA_ENDPOINTS.QUESTION(id), input)).data;
  },

  /** Staff only: show the question to students, or hide it (the Problems list's publish button). */
  async setPublished(id: number, published: boolean): Promise<void> {
    await api.post(`${RA_ENDPOINTS.QUESTION(id)}/${published ? 'publish' : 'unpublish'}`);
  },

  async deleteQuestion(id: number): Promise<void> {
    await api.delete(RA_ENDPOINTS.QUESTION(id));
  },

  /** Run an answer to one part step by step; not graded and not recorded. */
  async checkAnswer(id: number, partId: number, answer: string): Promise<RaCheckResponse> {
    return (await api.post<RaCheckResponse>(RA_ENDPOINTS.QUESTION_CHECK(id), { answer, part_id: partId })).data;
  },

  /** Grade an answer to one part and record the attempt. */
  async submitAnswer(id: number, partId: number, answer: string): Promise<RaSubmitResponse> {
    return (await api.post<RaSubmitResponse>(RA_ENDPOINTS.QUESTION_SUBMIT(id), { answer, part_id: partId })).data;
  },

  /** Multi-step questions: run every box on the shown data; not graded and not recorded. */
  async checkSteps(id: number, partId: number, stepAnswers: string[]): Promise<RaCheckResponse> {
    return (await api.post<RaCheckResponse>(RA_ENDPOINTS.QUESTION_CHECK(id),
      { step_answers: stepAnswers, part_id: partId })).data;
  },

  /** Multi-step questions: mark the boxes and record the attempt. */
  async submitSteps(id: number, partId: number, stepAnswers: string[]): Promise<RaSubmitResponse> {
    return (await api.post<RaSubmitResponse>(RA_ENDPOINTS.QUESTION_SUBMIT(id),
      { step_answers: stepAnswers, part_id: partId })).data;
  },

  /** Staff only: the form's type switch — every part rewritten for the new type; nothing is saved. */
  async convertFormat(schemaSql: string, fromFormat: RaAnswerFormat, toFormat: RaAnswerFormat,
    parts: Pick<RaPartInput, 'model_answer' | 'checkpoints' | 'steps' | 'marks'>[]): Promise<RaFormatConvertResponse> {
    return (await api.post<RaFormatConvertResponse>(RA_ENDPOINTS.QUESTIONS_CONVERT_FORMAT,
      { schema_sql: schemaSql, from_format: fromFormat, to_format: toFormat, parts })).data;
  },

  /** Staff only: the multi-step preview — mark boxes against the draft steps; nothing is saved. */
  async trySteps(input: { schema_sql: string; data_sql: string; example_data_sql: string | null;
    compare_bags: boolean; steps: RaStepSpecStaff[]; step_answers: string[] }): Promise<RaTryStepsResponse> {
    return (await api.post<RaTryStepsResponse>(RA_ENDPOINTS.QUESTIONS_TRY_STEPS, input)).data;
  },

  async myAttempts(id: number): Promise<RaAttempt[]> {
    return (await api.get<RaAttempt[]>(RA_ENDPOINTS.QUESTION_ATTEMPTS(id))).data;
  },
};
