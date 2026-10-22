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

// ── RA questions ──────────────────────────────────────────────────────────────
export type RaDifficulty = 'easy' | 'medium' | 'hard';

/** A model-answer step students' steps are compared with; `statement` null = the final answer. */
export interface RaCheckpoint {
  statement: string | null;
  label: string;
}

export interface RaQuestionListItem {
  id: number;
  title: string;
  difficulty: RaDifficulty;
  is_published: boolean;
  has_data: boolean;
  attempts: number;
  solved: boolean; // every part solved
  parts_total: number;
  parts_solved: number;
}

/** One part of a question, (i), (ii), …, as students see it (never its model answer). */
export interface RaPart {
  id: number;
  label: string; // '' for a question with a single part
  description: string;
  marks: number;
  attempts: number;
  solved: boolean;
  submissions_used: number;
}

export interface RaPartStaff extends RaPart {
  model_answer: string;
  checkpoints: RaCheckpoint[] | null;
  suite: RaSuiteSummary | null;
}

/** A question as students see it (never the model answer). */
export interface RaQuestion {
  id: number;
  title: string;
  description: string;
  difficulty: RaDifficulty;
  relations: RaRelation[];
  has_data: boolean;
  show_step_direction: boolean;
  hide_correctness: boolean;
  attempts: number;
  solved: boolean; // every part solved
  parts: RaPart[];
  /** Set when this is an assessment's copy of a question. */
  assessment_id: number | null;
  max_submissions: number | null; // per part; null = unlimited
}

export interface RaQuestionStaff extends Omit<RaQuestion, 'parts'> {
  schema_sql: string;
  data_sql: string;
  parts: RaPartStaff[];
  compare_bags: boolean;
  is_published: boolean;
  assessment_step_direction: boolean;
}

export interface RaPartInput {
  id: number | null; // an existing part keeps its id (and its students' attempts)
  label: string;
  description: string;
  marks: number;
  model_answer: string;
  checkpoints: RaCheckpoint[] | null;
}

export interface RaQuestionInput {
  title: string;
  description: string;
  difficulty: RaDifficulty;
  schema_sql: string;
  data_sql: string;
  parts: RaPartInput[];
  show_step_direction: boolean;
  assessment_step_direction: boolean;
  compare_bags: boolean;
  hide_correctness: boolean;
  is_published: boolean;
}

export type RaInputField = 'schema' | 'data' | 'model_answer' | 'checkpoints';

export interface RaValidateResponse {
  ok: boolean;
  error_source: RaInputField | null;
  error: RaError | null;
  relations: RaRelation[];
  suite: RaSuiteSummary | null;
  model_result: RaEvalResult | null;
  model_result_source: 'sample' | 'generated' | null;
  checkpoints: RaCheckpoint[];
}

/** An answer in textbook notation: one LaTeX line per statement, as the parser read it. */
export interface RaNotationResponse {
  ok: boolean;
  lines: { line: number | null; name: string | null; latex: string }[];
  error: RaError | null;
}

export interface RaSchemaTextResponse {
  ok: boolean;
  schema_sql: string;
  relations: RaRelation[];
  error: RaError | null;
}

export interface RaCheckResponse {
  ok: boolean;
  error: RaError | null;
  result: RaEvalResult | null;
  source: 'sample' | 'generated' | null;
  relations: RaRelation[];
}

export interface RaSubmitResponse {
  attempt_id: number;
  part_id: number;
  max_submissions: number | null;
  submissions_used: number;
  grade: RaGradeResult | null; // null when the question hides correctness
  structure: RaEvalResult | null;
  structure_source: 'sample' | 'generated' | null;
}

export interface RaAttempt {
  id: number;
  part_id: number | null;
  answer: string;
  verdict: RaVerdict | null;
  is_correct: boolean | null;
  created_at: string;
}

// ── staff analytics ─────────────────────────────────────────────────────────
export type RaVerdictCounts = Record<RaVerdict, number>;

/** A common error among unreadable answers: its code, one example message, how often. */
export interface RaTopError {
  code: string;
  example: string;
  count: number;
  students: number;
}

export interface RaClassAnalytics {
  totals: {
    submissions: number;
    students_engaged: number;
    registered_students: number;
    avg_completion_percent: number | null;
    questions: number;
  };
  verdicts: RaVerdictCounts;
  top_errors: RaTopError[];
  questions: {
    question_id: number;
    title: string;
    is_published: boolean;
    parts: number;
    attempts: number;
    students: number;
    students_solved: number;
    completion_rate: number | null;
    verdicts: RaVerdictCounts;
  }[];
  students: {
    user_id: number;
    email: string;
    name: string | null;
    class_group: string | null;
    submissions: number;
    questions_tried: number;
    parts_tried: number;
    parts_solved: number;
    completion_percent: number | null;
    first_activity_at: string | null;
    last_activity_at: string | null;
  }[];
}

export interface RaQuestionAnalytics {
  question_id: number;
  title: string;
  is_assessment_copy: boolean;
  student_count: number;
  solved_count: number;
  verdicts: RaVerdictCounts;
  top_errors: RaTopError[];
  parts: {
    part_id: number;
    label: string;
    marks: number;
    students: number;
    students_solved: number;
    attempts: number;
    avg_submits_to_correct: number | null;
    verdicts: RaVerdictCounts;
    top_errors: RaTopError[];
  }[];
  students: {
    user_id: number;
    email: string;
    name: string | null;
    class_group: string | null;
    attempts: number;
    parts_solved: number;
    marks_earned: number;
    marks_total: number;
    last_attempt_at: string | null;
    parts: {
      part_id: number;
      attempts: number;
      solved: boolean;
      submits_to_correct: number | null;
      last_verdict: RaVerdict | null;
    }[];
  }[];
}

export interface RaStudentAttempts {
  student_id: number;
  email: string;
  name: string | null;
  attempts: {
    id: number;
    part_id: number | null;
    part_label: string;
    created_at: string | null;
    answer: string;
    verdict: RaVerdict;
    correct: boolean;
    overridden: boolean;
    method: string | null;
    message: string;
    error: RaError | null;
  }[];
}
