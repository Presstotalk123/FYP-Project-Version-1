import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { GraphQuestionCreate, GraphQuestionResponse, GraphSolverQuestion } from '@/types/graph-question.types';
import { SqlLabRunResult, ItemGradeResult, DatabaseState } from '@/types/unified-lab.types';
import { AuthorQuestion, QuestionAuthoringService, SeedRebuildResult } from '@/types/question-author.types';

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
    // The graph /database endpoint returns the richer get_graph_schema_info shape
    // (node labels + relationship types as "tables", each with sample_data.rows).
    // Adapt it to the lean DatabaseState the solver renders (columns + sample_rows).
    const raw = (await api.get<{
      tables?: Array<{
        name: string;
        columns?: Array<{ name: string; type: string }>;
        row_count: number;
        sample_data?: { rows?: Array<Record<string, unknown>> };
      }>;
    }>(API_ENDPOINTS.GRAPH_QUESTIONS.DATABASE(id))).data;
    return {
      tables: (raw.tables ?? []).map((t) => ({
        name: t.name,
        columns: (t.columns ?? []).map((c) => ({ name: c.name, type: c.type })),
        row_count: t.row_count,
        sample_rows: t.sample_data?.rows ?? [],
      })),
    };
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

function toAuthorQuestion(q: GraphQuestionResponse): AuthorQuestion {
  return {
    id: q.id, title: q.title, description: q.description, difficulty: q.difficulty, status: q.status,
    seed: { seed_cypher: q.seed_cypher },
    tasks: q.tasks.map((t) => ({ id: t.id, title: t.title, description: t.description,
                                 order_index: t.order_index, has_answer: t.has_answer })),
  };
}

export const graphAuthoring: QuestionAuthoringService & {
  createDraft: (m: { title: string; description: string; difficulty: string }, seed: Record<string, string>) => Promise<{ id: number }>;
} = {
  async createDraft(m, seed) {
    const payload = { ...m, seed_cypher: seed.seed_cypher };
    const { data } = await api.post<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.BASE, payload);
    return { id: data.id };
  },
  async getById(id) { return toAuthorQuestion((await api.get<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.DETAIL(id))).data); },
  async updateMeta(id, patch) { return toAuthorQuestion((await api.patch<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.META(id), patch)).data); },
  async updateSeed(id, seed) { return (await api.put<SeedRebuildResult>(API_ENDPOINTS.GRAPH_QUESTIONS.SEED(id), seed)).data; },
  async addTask(id, body) { return toAuthorQuestion((await api.post<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.TASKS(id), body)).data); },
  async assignAnswer(id, taskId, query) { return toAuthorQuestion((await api.post<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.TASK_ASSIGN(id, taskId), { query })).data); },
  async updateTask(id, taskId, patch) { return toAuthorQuestion((await api.put<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.TASK_DETAIL(id, taskId), patch)).data); },
  async deleteTask(id, taskId) { return toAuthorQuestion((await api.delete<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.TASK_DETAIL(id, taskId))).data); },
  async reorderTasks(id, orderedIds) { return toAuthorQuestion((await api.put<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.TASK_REORDER(id), { ordered_ids: orderedIds })).data); },
  async finalize(id) { return toAuthorQuestion((await api.post<GraphQuestionResponse>(API_ENDPOINTS.GRAPH_QUESTIONS.FINALIZE(id))).data); },
  run: (id, query) => graphQuestionService.run(id, query),
  database: (id) => graphQuestionService.database(id),
  reset: (id) => graphQuestionService.reset(id),
};
