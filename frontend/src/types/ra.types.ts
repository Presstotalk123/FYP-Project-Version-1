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
  /** Staff only: how the proof went (whole | by_parts | search, or why it couldn't decide). */
  proof?: string | null;
}

/** How strong a question's generated test databases are. */
export interface RaSuiteSummary {
  databases: number;
  mutants: number;
  mutants_killed: number;
  candidates_tried: number;
  build_ms: number;
  /** ``equivalent``: the prover's view — true proved equivalent, false proved different, null undecided. */
  surviving_mutants: { description: string; line: number | null; text: string; equivalent?: boolean | null }[];
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
  created_by: number | null;
  created_at: string | null;
}

/**
 * How a question asks for its answer, chosen by staff for the whole question (students
 * never choose): mixed = steps or one expression, as before; final_answer = one expression
 * only; multi_step = one box per step the professor set.
 */
export type RaAnswerFormat = 'mixed' | 'final_answer' | 'multi_step';

/** One step of a multi-step part as students see it; the last one is the final answer (no name). */
export interface RaStepSpec {
  name: string | null;
  prompt: string;
  marks: number;
}

export interface RaStepSpecStaff extends RaStepSpec {
  model_answer: string;
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
  steps: RaStepSpec[] | null; // multi-step questions
}

export interface RaPartStaff extends RaPart {
  model_answer: string;
  checkpoints: RaCheckpoint[] | null;
  suite: RaSuiteSummary | null;
  steps: RaStepSpecStaff[] | null;
}

/** A question as students see it (never the model answer). */
export interface RaQuestion {
  id: number;
  title: string;
  description: string;
  difficulty: RaDifficulty;
  relations: RaRelation[];
  has_data: boolean; // the question has data of its own
  /** Where the tuples in ``relations`` come from: the question's data, or example data built for it. */
  data_source: 'sample' | 'example' | null;
  answer_format: RaAnswerFormat;
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
  example_data_sql: string | null; // what students see while data_sql is empty
  parts: RaPartStaff[];
  compare_bags: boolean;
  is_published: boolean;
  assessment_step_direction: boolean;
  has_attempts: boolean; // answered already: the type can't change any more
}

export interface RaPartInput {
  id: number | null; // an existing part keeps its id (and its students' attempts)
  label: string;
  description: string;
  marks: number;
  model_answer: string;
  checkpoints: RaCheckpoint[] | null;
  steps: RaStepSpecStaff[] | null; // multi-step questions (the model answer is built from them)
}

export interface RaQuestionInput {
  title: string;
  description: string;
  difficulty: RaDifficulty;
  schema_sql: string;
  data_sql: string;
  /** With data_sql empty: the example data shown in the form (null = keep or build it). */
  example_data_sql: string | null;
  parts: RaPartInput[];
  /** null until the professor picks one for a new question (nothing is preselected). */
  answer_format: RaAnswerFormat | null;
  show_step_direction: boolean;
  assessment_step_direction: boolean;
  compare_bags: boolean;
  hide_correctness: boolean;
  is_published: boolean;
}

export type RaInputField = 'schema' | 'data' | 'model_answer' | 'checkpoints' | 'steps' | 'answer_format';

export interface RaValidateResponse {
  ok: boolean;
  error_source: RaInputField | null;
  error: RaError | null;
  error_step: number | null; // which step, for a multi-step part
  relations: RaRelation[];
  suite: RaSuiteSummary | null;
  model_result: RaEvalResult | null;
  model_result_source: 'sample' | 'example' | 'generated' | null;
  checkpoints: RaCheckpoint[];
}

export interface RaExampleDataResponse {
  ok: boolean;
  data_sql: string;
  relations: RaRelation[];
  error: RaError | null;
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
  source: 'sample' | 'example' | 'generated' | null;
  relations: RaRelation[];
  boxes?: RaBoxCheck[] | null; // multi-step questions, instead of result
}

/** One box of a multi-step answer, run on the shown data. */
export interface RaBoxCheck {
  status: 'empty' | 'error' | 'ok';
  error: RaError | null;
  step: RaStep | null;
}

/** One step of a multi-step answer after Submit. */
export interface RaStepResult {
  index: number;
  name: string | null;
  prompt: string;
  marks: number;
  earned: number;
  /** full: the final answer is correct · reached: a box computes it · carried: a box
   *  computes it given the model's earlier steps · missed */
  status: 'full' | 'reached' | 'carried' | 'missed';
  credited_by: number | null; // the box that earned it (0-based)
  box_status: 'empty' | 'error' | 'ok';
  box_error: RaError | null;
  feedback: RaStepFeedback | null; // ✓/◐/○ for this box ('none' when hidden)
  structure: RaStep | null; // the box on the shown data
  student: { columns: string[]; rows: unknown[][] } | null; // a missed step: the box's table…
  expected: { columns: string[]; rows: unknown[][] } | null; // …and the model step's
}

export interface RaStepMarking {
  earned: number;
  total: number;
  final_correct: boolean;
  source: 'sample' | 'example' | 'generated' | null;
  steps: RaStepResult[];
}

export interface RaConvertedPart {
  model_answer: string;
  checkpoints: RaCheckpoint[] | null;
  steps: RaStepSpecStaff[] | null;
  marks: number;
  error: string | null; // couldn't convert: rewrite it by hand
}

export interface RaFormatConvertResponse {
  ok: boolean;
  error: RaError | null;
  parts: RaConvertedPart[];
}

export interface RaTryStepsResponse {
  ok: boolean;
  error_source: 'schema' | 'data' | 'steps' | null;
  error: RaError | null;
  error_step: number | null;
  grade: RaGradeResult | null;
  marking: RaStepMarking | null;
}

/** After Submit: the student's result and the model answer's on the data shown with the question. */
export interface RaShownResult {
  source: 'sample' | 'example';
  same_columns: boolean;
  equal: boolean;
  student: { columns: string[]; rows: unknown[][] };
  expected: { columns: string[]; rows: unknown[][] };
  student_extra: boolean[]; // row i of the student's result shouldn't be there
  expected_missing: boolean[]; // row i of the model answer's result is missing from theirs
}

export interface RaSubmitResponse {
  attempt_id: number;
  part_id: number;
  max_submissions: number | null;
  submissions_used: number;
  grade: RaGradeResult | null; // null when the question hides correctness
  structure: RaEvalResult | null;
  structure_source: 'sample' | 'example' | 'generated' | null;
  shown: RaShownResult | null; // only with grade
  marking?: RaStepMarking | null; // multi-step questions, only with grade
}

export interface RaAttempt {
  id: number;
  part_id: number | null;
  answer: string;
  verdict: RaVerdict | null;
  is_correct: boolean | null;
  created_at: string;
  step_answers: string[] | null; // multi-step questions: the boxes
  marks_earned: number | null; // multi-step questions (null when correctness is hidden)
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
    /** Of the answers marked correct: proved equivalent to the model answer, or only tested. */
    correct_by: { proved: number; tested: number };
    /** Multi-step parts: how far students got (their best Submit). */
    steps: RaStepProgress[] | null;
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
      marks_earned: number;
      submits_to_correct: number | null;
      last_verdict: RaVerdict | null;
    }[];
  }[];
}

export interface RaStepProgress {
  index: number;
  name: string | null;
  prompt: string;
  marks: number;
  reached: number; // students whose best Submit earned this step
  carried: number; // …of them, through carry-forward
  missed: number;
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
    databases_checked: number;
    message: string;
    error: RaError | null;
  }[];
  /** The student's conversation with Bagheera on this question (staff see held-back replies). */
  bagheera: RaBagheeraMessage[];
}

/** One message between a student and Bagheera, the AI tutor (hints only; it never grades). */
export interface RaBagheeraMessage {
  id: number;
  part_id: number | null;
  kind: 'chat' | 'explain';
  role: 'user' | 'assistant';
  content: string;
  /** "Explain my mistake": the attempt explained. */
  attempt_id: number | null;
  /** The first reply gave the answer away, so this one replaced it. */
  guarded: boolean;
  /** Staff only: what was held back. */
  blocked_content?: string | null;
  created_at: string | null;
}

export interface RaBagheeraState {
  available: boolean;
  /** Why Bagheera is off here (assessment, hidden correctness, not set up). */
  reason: string | null;
  messages: RaBagheeraMessage[];
}

/** One past attempt whose result the current grader would change. */
export interface RaRegradeChange {
  attempt_id: number;
  part_id: number;
  user_id: number;
  student: string;
  email: string;
  answer: string;
  created_at: string | null;
  old: { verdict: RaVerdict; correct: boolean; method: string | null; marks_earned: number | null };
  new: { verdict: RaVerdict; correct: boolean; method: string | null; marks_earned: number | null };
  /** False when only the method changed (e.g. now proved instead of tested). */
  verdict_changed: boolean;
  /** A staff override decides this attempt's marks whatever the grader says. */
  overridden: boolean;
}

export interface RaRegradePreview {
  total: number;
  checked: number;
  after_id: number | null;
  done: boolean;
  changes: RaRegradeChange[];
}
