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
}
