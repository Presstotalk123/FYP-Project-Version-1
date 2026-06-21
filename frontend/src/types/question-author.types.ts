import { SqlLabRunResult, DatabaseState } from './unified-lab.types';

export interface AuthorTaskView {
  id: number;
  title: string;
  description: string;
  order_index: number;
  has_answer: boolean;
}

export interface AuthorQuestion {
  id: number;
  title: string;
  description: string;
  difficulty: string;
  status: 'draft' | 'ready' | string;
  seed: Record<string, string>;   // e.g. { schema_sql, sample_data_sql } or { seed_cypher }
  tasks: AuthorTaskView[];
}

export interface SeedRebuildResult {
  status: string;
  warnings: string[];
}

/** Everything the shared author workspace needs, wired per question type. */
export interface QuestionAuthoringService {
  getById(id: number): Promise<AuthorQuestion>;
  updateMeta(id: number, patch: { title?: string; description?: string; difficulty?: string }): Promise<AuthorQuestion>;
  updateSeed(id: number, seed: Record<string, string>): Promise<SeedRebuildResult>;
  addTask(id: number, body: { title: string; description: string }): Promise<AuthorQuestion>;
  assignAnswer(id: number, taskId: number, query: string): Promise<AuthorQuestion>;
  updateTask(id: number, taskId: number, patch: { title?: string; description?: string }): Promise<AuthorQuestion>;
  deleteTask(id: number, taskId: number): Promise<AuthorQuestion>;
  reorderTasks(id: number, orderedIds: number[]): Promise<AuthorQuestion>;
  finalize(id: number): Promise<AuthorQuestion>;
  run(id: number, query: string): Promise<SqlLabRunResult>;
  database(id: number): Promise<DatabaseState>;
  reset(id: number): Promise<void>;
}

export interface SeedField {
  key: string;            // matches a key in AuthorQuestion.seed
  label: string;
  language: 'sql' | 'cypher';
}

export interface QuestionAuthorConfig {
  editorLanguage: 'sql' | 'cypher';
  seedFields: SeedField[];
  service: QuestionAuthoringService;
  poolHref: string;       // where to return after finalize, e.g. '/problems'
  createDraft: (meta: { title: string; description: string; difficulty: string }, seed: Record<string, string>) => Promise<{ id: number }>;
  newAuthorHref: (id: number) => string;  // e.g. (id) => `/sql-lab/${id}/author`
}
