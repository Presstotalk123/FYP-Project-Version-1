import api from '@/services/api.service';
import {
  RaAttempt, RaCheckpoint, RaCheckResponse, RaExample, RaNotationResponse, RaPlaygroundGradeResponse,
  RaPlaygroundRunResponse, RaQuestion, RaPartInput, RaQuestionInput, RaQuestionListItem, RaQuestionStaff,
  RaSchemaTextResponse, RaStatus, RaSubmitResponse, RaValidateResponse,
} from '@/types/ra.types';

/** RA endpoints, relative to the shared API base URL (…/api/v1). */
export const RA_ENDPOINTS = {
  STATUS: '/ra/status',
  PLAYGROUND_EXAMPLES: '/ra/playground/examples',
  PLAYGROUND_RUN: '/ra/playground/run',
  PLAYGROUND_GRADE: '/ra/playground/grade',
  NOTATION: '/ra/notation',
  QUESTIONS: '/ra/questions',
  QUESTIONS_VALIDATE: '/ra/questions/validate',
  QUESTIONS_SCHEMA_FROM_TEXT: '/ra/questions/schema-from-text',
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
  async validateQuestion(input: Pick<RaQuestionInput, 'schema_sql' | 'data_sql' | 'compare_bags'>
    & Pick<RaPartInput, 'model_answer' | 'checkpoints'>): Promise<RaValidateResponse> {
    return (await api.post<RaValidateResponse>(RA_ENDPOINTS.QUESTIONS_VALIDATE, input)).data;
  },

  /** The answer in textbook notation (σ with its condition as a subscript …), for the editor's preview. */
  async notation(program: string, names: string[] = []): Promise<RaNotationResponse> {
    return (await api.post<RaNotationResponse>(RA_ENDPOINTS.NOTATION, { program, names })).data;
  },

  /** Staff only: turn a schema written as text (``STUDENT(*Sid, Sname)``) into CREATE TABLE statements. */
  async schemaFromText(text: string, linkKeys: boolean): Promise<RaSchemaTextResponse> {
    return (await api.post<RaSchemaTextResponse>(RA_ENDPOINTS.QUESTIONS_SCHEMA_FROM_TEXT,
      { text, link_keys: linkKeys })).data;
  },

  async createQuestion(input: RaQuestionInput): Promise<RaQuestionStaff> {
    return (await api.post<RaQuestionStaff>(RA_ENDPOINTS.QUESTIONS, input)).data;
  },

  async updateQuestion(id: number, input: RaQuestionInput): Promise<RaQuestionStaff> {
    return (await api.put<RaQuestionStaff>(RA_ENDPOINTS.QUESTION(id), input)).data;
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

  async myAttempts(id: number): Promise<RaAttempt[]> {
    return (await api.get<RaAttempt[]>(RA_ENDPOINTS.QUESTION_ATTEMPTS(id))).data;
  },
};
