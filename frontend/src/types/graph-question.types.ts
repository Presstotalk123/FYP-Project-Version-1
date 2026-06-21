import { Difficulty } from './question.types';

export interface GraphTaskInput {
  title: string;
  description: string;
  correct_query: string;
}

export interface GraphQuestionCreate {
  title: string;
  description: string;
  difficulty: Difficulty;
  seed_cypher: string;
  tasks: GraphTaskInput[];
}

export interface GraphTaskView {
  id: number;
  title: string;
  description: string;
  order_index: number;
  has_answer: boolean;
}

export interface GraphQuestionResponse {
  id: number;
  title: string;
  description: string;
  difficulty: string;
  seed_cypher: string;
  created_by: number;
  created_at: string;
  tasks: GraphTaskView[];
}

// Shape the SqlLabSolver needs, derived from a question (lab + standalone use the same).
// Graph reuses the solver shape: seed_cypher is mapped into schema_sql for the left panel,
// and sample_data_sql is left empty since a graph question has a single seed field.
export interface GraphSolverQuestion {
  title: string;
  description: string;
  schema_sql: string;
  sample_data_sql: string;
  tasks: { id: number; title: string; description: string; order_index: number }[];
}
