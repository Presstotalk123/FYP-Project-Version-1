import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { GraphQuestionCreate, GraphQuestionResponse, GraphSolverQuestion } from '@/types/graph-question.types';
import { SqlLabRunResult, ItemGradeResult, DatabaseState } from '@/types/unified-lab.types';

export const graphQuestionService = {
  async create(payload: GraphQuestionCreate): Promise<GraphQuestionResponse> {
    return (await api.post<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.BASE, payload)).data;
  },
  async getById(id: number): Promise<GraphQuestionResponse> {
    return (await api.get<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.DETAIL(id))).data;
  },
  async remove(id: number): Promise<void> {
    await api.delete(API_ENDPOINTS.GRAPH_QUESTIONS.DETAIL(id));
  },
  async run(id: number, query: string): Promise<SqlLabRunResult> {
    return (await api.post<SqlLabRunResult>(API_ENDPOINTS.GRAPH_QUESTIONS.RUN(id), { query })).data;
  },
  async submit(id: number, query: string, taskId: number): Promise<ItemGradeResult> {
    return (await api.post<ItemGradeResult>(API_ENDPOINTS.GRAPH_QUESTIONS.SUBMIT(id), { query, task_id: taskId })).data;
  },
  async database(id: number): Promise<DatabaseState> {
    return (await api.get<DatabaseState>(API_ENDPOINTS.GRAPH_QUESTIONS.DATABASE(id))).data;
  },
  async reset(id: number): Promise<void> {
    await api.post(API_ENDPOINTS.GRAPH_QUESTIONS.RESET(id));
  },
  async loadForSolver(id: number): Promise<GraphSolverQuestion> {
    const q = await this.getById(id);
    return {
      title: q.title, description: q.description, schema_sql: q.seed_cypher, sample_data_sql: '',
      tasks: q.tasks.map((t) => ({ id: t.id, title: t.title, description: t.description, order_index: t.order_index })),
    };
  },
};
