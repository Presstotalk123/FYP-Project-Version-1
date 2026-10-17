/** Relational Algebra types — mirror backend/app/schemas/ra.py (no codegen; keep in sync). */

export interface RaStatus {
  enabled: boolean;
  aggregate_nulls: 'sql' | 'slides';
}

export interface RaError {
  code: string;
  message: string;
  line?: number | null;
  col?: number | null;
  hint?: string | null;
}

/** One relation of a schema, with its tuples. */
export interface RaRelation {
  name: string;
  columns: string[];
  types: string[];
  primary_key: string[];
  rows: unknown[][];
}

/** One node of an evaluated expression, with its intermediate result. */
export interface RaStepNode {
  op: string;
  label: string;
  columns: string[];
  row_count: number;
  rows: unknown[][]; // first 50 tuples
  children: RaStepNode[];
  line?: number | null;
  col?: number | null;
}

/** One statement of the answer: `R1 := …` (name) or the final expression (name null). */
export interface RaStep {
  name: string | null;
  line?: number | null;
  tree: RaStepNode;
}

export interface RaEvalResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  steps: RaStep[];
  warnings: RaError[];
}

export interface RaPlaygroundRunResponse {
  ok: boolean;
  error_source: 'schema' | 'expression' | null;
  error: RaError | null;
  relations: RaRelation[];
  result: RaEvalResult | null;
  elapsed_ms: number;
}

export interface RaExample {
  id: string;
  title: string;
  description: string;
  schema_sql: string;
  data_sql: string;
  expressions: string[];
  grading_examples: RaGradingExample[];
}

export interface RaGradingExample {
  title: string;
  model_answer: string;
  answer: string;
}

/** A small database plus what each answer returns on it. */
export interface RaCase {
  tables: Record<string, { columns: string[]; rows: unknown[][] }>;
  expected: { columns: string[]; rows: unknown[][] };
  student: { columns: string[]; rows: unknown[][] };
  missing?: unknown[][];
  extra?: unknown[][];
}

/** One statement of the student's answer compared with the model answer's steps. */
export interface RaStepFeedback {
  name: string | null;
  line: number | null;
  text: string;
  columns: string[];
  status: 'match' | 'close' | 'none';
  checkpoint: string | null;
  renamed: boolean;
  case: RaCase | null;
}

export type RaVerdict = 'correct' | 'wrong_columns' | 'wrong_result' | 'wrong_in_general' | 'invalid_expression';

export interface RaGradeResult {
  verdict: RaVerdict;
  message: string;
  method: 'proof' | 'tested' | 'sample' | null;
  expected_columns: string[];
  student_columns: string[];
  databases_checked: number;
  missing_count: number;
  extra_count: number;
  extra_rows: unknown[][];
  counterexample: RaCase | null;
  steps: RaStepFeedback[];
  error: RaError | null;
  elapsed_ms: number;
}

/** How strong a question's generated test databases are. */
export interface RaSuiteSummary {
  databases: number;
  mutants: number;
  mutants_killed: number;
  candidates_tried: number;
  build_ms: number;
  surviving_mutants: { description: string; line: number | null; text: string }[];
}

export interface RaPlaygroundGradeResponse {
  ok: boolean;
  error_source: 'schema' | 'model' | null;
  error: RaError | null;
  grade: RaGradeResult | null;
  suite: RaSuiteSummary | null;
  structure: RaEvalResult | null;
  structure_source: 'sample' | 'generated' | null;
  structure_relations: RaRelation[];
}
