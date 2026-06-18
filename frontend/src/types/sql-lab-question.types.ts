import { Difficulty } from './question.types';

export interface SqlLabTaskInput {
  title: string;
  description: string;
  correct_query: string;
}

export interface SqlLabQuestionCreate {
  title: string;
  description: string;
  difficulty: Difficulty;
  schema_sql: string;
  sample_data_sql: string;
  tasks: SqlLabTaskInput[];
}

export interface SqlLabTaskView {
  id: number;
  title: string;
  description: string;
  order_index: number;
  has_answer: boolean;
}

export interface SqlLabQuestionResponse {
  id: number;
  title: string;
  description: string;
  difficulty: string;
  schema_sql: string;
  sample_data_sql: string;
  created_by: number;
  created_at: string;
  tasks: SqlLabTaskView[];
}

// Shape the SqlLabSolver needs, derived from a question (lab + standalone use the same).
export interface SqlLabSolverQuestion {
  title: string;
  description: string;
  schema_sql: string;
  sample_data_sql: string;
  tasks: { id: number; title: string; description: string; order_index: number }[];
}
