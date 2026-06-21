import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { SqlLabQuestionCreate, SqlLabQuestionResponse, SqlLabSolverQuestion } from '@/types/sql-lab-question.types';
import { SqlLabRunResult, ItemGradeResult, DatabaseState } from '@/types/unified-lab.types';
import { AuthorQuestion, QuestionAuthoringService, SeedRebuildResult } from '@/types/question-author.types';

export const sqlLabQuestionService = {
  async create(payload: SqlLabQuestionCreate): Promise<SqlLabQuestionResponse> {
    return (await api.post<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.BASE, payload)).data;
  },
  async getById(id: number): Promise<SqlLabQuestionResponse> {
    return (await api.get<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.DETAIL(id))).data;
  },
  async remove(id: number): Promise<void> {
    await api.delete(API_ENDPOINTS.SQL_LAB_QUESTIONS.DETAIL(id));
  },
  async run(id: number, query: string): Promise<SqlLabRunResult> {
    return (await api.post<SqlLabRunResult>(API_ENDPOINTS.SQL_LAB_QUESTIONS.RUN(id), { query })).data;
  },
  async submit(id: number, query: string, taskId: number): Promise<ItemGradeResult> {
    return (await api.post<ItemGradeResult>(API_ENDPOINTS.SQL_LAB_QUESTIONS.SUBMIT(id), { query, task_id: taskId })).data;
  },
  async database(id: number): Promise<DatabaseState> {
    return (await api.get<DatabaseState>(API_ENDPOINTS.SQL_LAB_QUESTIONS.DATABASE(id))).data;
  },
  async reset(id: number): Promise<void> {
    await api.post(API_ENDPOINTS.SQL_LAB_QUESTIONS.RESET(id));
  },
  async loadForSolver(id: number): Promise<SqlLabSolverQuestion> {
    const q = await this.getById(id);
    return {
      title: q.title, description: q.description, schema_sql: q.schema_sql, sample_data_sql: q.sample_data_sql,
      tasks: q.tasks.map((t) => ({ id: t.id, title: t.title, description: t.description, order_index: t.order_index })),
    };
  },
};

function toAuthorQuestion(q: SqlLabQuestionResponse): AuthorQuestion {
  return {
    id: q.id, title: q.title, description: q.description, difficulty: q.difficulty, status: q.status,
    seed: { schema_sql: q.schema_sql, sample_data_sql: q.sample_data_sql },
    tasks: q.tasks.map((t) => ({ id: t.id, title: t.title, description: t.description,
                                 order_index: t.order_index, has_answer: t.has_answer })),
  };
}

export const sqlLabAuthoring: QuestionAuthoringService & {
  createDraft: (m: { title: string; description: string; difficulty: string }, seed: Record<string, string>) => Promise<{ id: number }>;
} = {
  async createDraft(m, seed) {
    const payload = { ...m, schema_sql: seed.schema_sql, sample_data_sql: seed.sample_data_sql };
    const { data } = await api.post<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.BASE, payload);
    return { id: data.id };
  },
  async getById(id) { return toAuthorQuestion((await api.get<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.DETAIL(id))).data); },
  async updateMeta(id, patch) { return toAuthorQuestion((await api.patch<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.META(id), patch)).data); },
  async updateSeed(id, seed) { return (await api.put<SeedRebuildResult>(API_ENDPOINTS.SQL_LAB_QUESTIONS.SEED(id), seed)).data; },
  async addTask(id, body) { return toAuthorQuestion((await api.post<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.TASKS(id), body)).data); },
  async assignAnswer(id, taskId, query) { return toAuthorQuestion((await api.post<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.TASK_ASSIGN(id, taskId), { query })).data); },
  async updateTask(id, taskId, patch) { return toAuthorQuestion((await api.put<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.TASK_DETAIL(id, taskId), patch)).data); },
  async deleteTask(id, taskId) { return toAuthorQuestion((await api.delete<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.TASK_DETAIL(id, taskId))).data); },
  async reorderTasks(id, orderedIds) { return toAuthorQuestion((await api.put<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.TASK_REORDER(id), { ordered_ids: orderedIds })).data); },
  async finalize(id) { return toAuthorQuestion((await api.post<SqlLabQuestionResponse>(API_ENDPOINTS.SQL_LAB_QUESTIONS.FINALIZE(id))).data); },
  run: (id, query) => sqlLabQuestionService.run(id, query),
  database: (id) => sqlLabQuestionService.database(id),
  reset: (id) => sqlLabQuestionService.reset(id),
};
