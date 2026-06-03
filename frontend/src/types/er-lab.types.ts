export type DifficultyLabel = 'Easy' | 'Medium' | 'Hard';

export interface ErLabResponse {
  id: number;
  title: string;
  description: string;
  is_published: boolean;
  is_running: boolean;
  created_at: string;
  updated_at: string;
}

export interface ErLabStaffDetail extends ErLabResponse {
  join_password: string;
}

export interface ErLabQuestionResponse {
  id: number;
  er_lab_id: number;
  order_index: number;
  title: string;
  problem_statement: string;
  notation: 'Chen';
  difficulty_label: DifficultyLabel;
  difficulty_rationale: string;
  rubric_md: string | null;
  rubric_json: Record<string, unknown> | null;
  instruction_history: string[];
  model_answer_storage_key: string | null;
  model_answer_url: string | null;
  show_rubric_on_attempt: boolean;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface ErLabSessionResponse {
  id: number;
  er_lab_id: number;
  user_id: number;
  is_active: boolean;
  started_at: string;
  ended_at: string | null;
}

export interface ErLabSubmissionResponse {
  id: number;
  er_lab_question_id: number;
  er_lab_id: number;
  user_id: number;
  session_id: number;
  submitted_xml: string | null;
  submitted_image_storage_key: string | null;
  auto_score_earned: number;
  auto_score_total: number;
  auto_score_percent: number;
  auto_score_label: string;
  auto_checks_json: unknown;
  auto_graded_at: string;
  override_score_earned: number | null;
  override_score_total: number | null;
  override_score_percent: number | null;
  override_reason: string | null;
  overridden_by: number | null;
  overridden_at: string | null;
  submitted_at: string;
}

export interface ErLabQuestionBestScore {
  er_lab_question_id: number;
  best_percent: number | null;
  best_earned: number | null;
  best_total: number | null;
  attempts: number;
  last_attempted_at: string | null;
}

export interface ErLabMyScoresResponse {
  er_lab_id: number;
  user_id: number;
  questions: ErLabQuestionBestScore[];
  total_earned: number;
  total_total: number;
}

export interface ErLabStudentSummary {
  user_id: number;
  email: string;
  total_earned: number;
  total_total: number;
  attempts: number;
  last_submission_at: string | null;
}

export interface ErLabStudentsResponse {
  er_lab_id: number;
  lab_title: string;
  total_questions: number;
  students: ErLabStudentSummary[];
}
