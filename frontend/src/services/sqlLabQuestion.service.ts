import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { SqlLabQuestionCreate, SqlLabQuestionResponse, SqlLabSolverQuestion } from '@/types/sql-lab-question.types';
import { SqlLabRunResult, ItemGradeResult, DatabaseState } from '@/types/unified-lab.types';

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
