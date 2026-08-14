export type AssessmentItemType = 'sql_question' | 'er_question' | 'sql_lab' | 'graph_lab';

export interface AssessmentItemIn {
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
  weight: number;
  // Per-item override: when true, students see a neutral "Submitted" result instead of
  // Correct/Incorrect. Applies to sql_question / sql_lab / graph_lab; ignored for er_question.
  hide_correctness: boolean;
  // Per-item cap on how many queries a student may run on this SQL question; null = unlimited.
  // Only meaningful for sql_question items.
  max_queries?: number | null;
}

export interface AssessmentItemResponse {
  id: number;
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
  weight: number;
  hide_correctness: boolean;
  max_queries?: number | null;
  item_title: string;
}

export interface Assessment {
  id: number;
  title: string;
  description: string | null;
  is_published: boolean;
  is_running: boolean;
  item_count: number;
  has_password: boolean;
  time_limit_minutes: number | null;
  // Timing Gateway master toggle — when true, access is driven by per-class-group windows.
  gateway_enabled?: boolean;
  created_at: string;
  updated_at: string | null;
}

// Timing Gateway (per-class-group access windows)
export type GatewayState = 'disabled' | 'no_window' | 'upcoming' | 'open' | 'closed';
export type ClassWindowStatus = 'upcoming' | 'active' | 'completed';

export interface ClassWindowIn {
  class_group: string;
  start_at: string; // ISO UTC
  end_at: string;   // ISO UTC
  is_enabled: boolean;
}

export interface ClassWindowOut extends ClassWindowIn {
  id: number;
  status: ClassWindowStatus;
  active_session_count: number;
}

export interface GatewayConfigUpdate {
  gateway_enabled: boolean;
  windows: ClassWindowIn[];
}

export interface GatewayConfigResponse {
  assessment_id: number;
  gateway_enabled: boolean;
  windows: ClassWindowOut[];
  warnings: string[];
}

export interface AssessmentDetail {
  id: number;
  title: string;
  description: string | null;
  is_published: boolean;
  is_running: boolean;
  items: AssessmentItemResponse[];
  created_by: number;
  password: string | null;
  has_password: boolean;
  time_limit_minutes: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface AssessmentCreate {
  title: string;
  description?: string;
  items: AssessmentItemIn[];
  password?: string;
  time_limit_minutes?: number | null;
}

export interface AssessmentUpdate {
  title?: string;
  description?: string;
  items?: AssessmentItemIn[];
  password?: string;
  clear_password?: boolean;
  time_limit_minutes?: number | null;
  clear_time_limit?: boolean;
}

// Student-side assessment types

export interface StudentAssessmentListItem {
  id: number;
  title: string;
  description: string | null;
  is_running: boolean;
  has_password: boolean;
  // True once this student has submitted this assessment (single-attempt).
  attempt_complete?: boolean;
  // Overall weighted score (0-100); null until staff release results (assessment stopped).
  weighted_score?: number | null;
  // When the student submitted; null if not yet completed. Used to order recent results.
  submitted_at?: string | null;
}

export interface StudentAssessmentItemView {
  id: number;
  item_type: AssessmentItemType;
  item_id: number;
  order_index: number;
  weight: number;
  item_title: string;
  visited: boolean;
}

export interface StudentAssessmentDetail {
  id: number;
  title: string;
  description: string | null;
  is_running: boolean;
  has_password: boolean;
  // Optional whole-minute time limit; null = untimed. Shown on the Begin screen.
  time_limit_minutes: number | null;
  // True once this student has ended & submitted; UI shows a Completed state and
  // hides Join/Continue (assessments are single-attempt).
  attempt_complete: boolean;
  // Overall weighted score (0-100). Only set once staff have stopped the assessment
  // (results released); null while it is still running or when unweighted.
  weighted_score: number | null;
  items: StudentAssessmentItemView[];
  // Timing Gateway: when enabled, the student's class-group window governs access.
  gateway_enabled?: boolean;
  gateway_state?: GatewayState | null;
  window_start?: string | null; // ISO UTC — when the student's window opens
  window_end?: string | null;   // ISO UTC — when the student's window closes
}

export interface AssessmentSessionResponse {
  id: number;
  assessment_id: number;
  user_id: number;
  is_active: boolean;
  joined_at: string;
  submitted_at: string | null;
  // Deadline for this attempt (ISO); null = untimed. The countdown ticks toward this.
  end_time: string | null;
  // Immovable Timing-Gateway cap (class-group window end, ISO); null when gateway off.
  // The countdown targets the earlier of end_time and hard_deadline.
  hard_deadline?: string | null;
}

export interface ItemVisitResponse {
  session_id: number;
  assessment_item_id: number;
  first_visited_at: string;
}

export interface AssessmentStudentRow {
  user_id: number;
  email: string;
  // Optional lab/class group the student belongs to.
  class_group?: string | null;
  is_active: boolean;
  joined_at: string;
  submitted_at: string | null;
  // Weighted total (0-100) from the student's activity; null if the assessment is unweighted.
  weighted_score?: number | null;
}

export interface AssessmentStudentsResponse {
  assessment_id: number;
  assessment_title: string;
  students: AssessmentStudentRow[];
}

// Whether one specific lab task was solved by one specific student.
export interface StudentLabTaskResult {
  task_id: number;
  task_title: string;
  order_index: number;
  correct: boolean;
}

export interface AssessmentItemComponentScore {
  assessment_item_id: number;
  item_type: AssessmentItemType;
  item_id: number;
  item_title: string;
  order_index: number;
  has_correct_attempt?: boolean | null;
  attempt_count?: number | null;
  tasks_correct?: number | null;
  tasks_total?: number | null;
  visited?: boolean | null;
  weight?: number;
  score_fraction?: number | null;
  weighted_points?: number | null;
  // Lab items only: per-task ✓/✗ for this student. Only populated by the staff report.
  tasks?: StudentLabTaskResult[] | null;
}

export interface StudentComponentScoresResponse {
  student_id: number;
  student_email: string;
  assessment_id: number;
  assessment_title: string;
  items: AssessmentItemComponentScore[];
  total_weighted_score?: number | null;
}

export interface LabTaskAggregateScore {
  task_id: number;
  task_title: string;
  order_index: number;
  // % of the roster who solved this specific task (0-100); null if the roster is empty.
  success_rate?: number | null;
  // Headcounts behind success_rate: students who solved it, students who submitted at
  // least once, and every submission they made.
  correct_count?: number;
  attempted_count?: number;
  total_attempts?: number;
}

export interface AssessmentItemAggregateScore {
  assessment_item_id: number;
  item_type: AssessmentItemType;
  item_id: number;
  item_title: string;
  order_index: number;
  weight?: number;
  // Mean correctness fraction (0.0-1.0) across the roster; null if the roster is empty.
  avg_score_fraction?: number | null;
  avg_weighted_points?: number | null;
  // Lab items only: mean distinct-correct-tasks per student, and the lab's total task count.
  avg_tasks_correct?: number | null;
  tasks_total?: number | null;
  // Lab items only: per-task success rate across the roster.
  tasks?: LabTaskAggregateScore[] | null;
  // Students who got this item fully right: a correct attempt (sql_question), every task
  // solved (labs), a "pass" grade (er_question).
  correct_count?: number;
  // Students who submitted at least once, and their total submissions. ER attempts come
  // from er_submissions, which only the LangGraph engine writes.
  attempted_count?: number;
  total_attempts?: number;
  // Mean attempts among students who attempted; null when nobody did.
  avg_attempts?: number | null;
}

export interface AssessmentItemAnalyticsResponse {
  assessment_id: number;
  assessment_title: string;
  // null when unfiltered (cohort-wide); set to the selected class_group otherwise.
  class_group?: string | null;
  student_count: number;
  // Students expected to sit this assessment, narrowed to class_group when one is selected.
  // The shared denominator for every item's attempted_count.
  registered_count?: number;
  avg_weighted_score?: number | null;
  // Class groups present in this assessment's roster — the group filter's options. Sent with
  // the analytics so the dashboard needn't fetch the whole roster to populate a dropdown.
  class_groups?: string[];
  items: AssessmentItemAggregateScore[];
}

// One assessment's headline numbers for the admin dashboard index.
export interface AssessmentAnalyticsSummaryRow {
  assessment_id: number;
  title: string;
  is_published: boolean;
  question_count: number;
  registered_count: number;
  // Students who opened the assessment — not the same as having attempted anything.
  started_count: number;
  avg_weighted_score?: number | null;
}

export interface AssessmentAnalyticsSummaryResponse {
  // Platform-wide counts for the Overview tab's metric card.
  platform_registered: number;
  platform_signed_in: number;
  assessments: AssessmentAnalyticsSummaryRow[];
}

// One student's outcome on one assessment question.
export type ItemStudentStatus = 'not_started' | 'not_attempted' | 'graded';

export interface ItemStudentRow {
  email: string;
  name?: string | null;
  class_group?: string | null;
  status: ItemStudentStatus;
  // 0-100. null only when status is 'not_started'.
  score_percent?: number | null;
  // "3/4 tasks", "Correct", "Incorrect"; null for ER items.
  detail?: string | null;
  attempts: number;
}

export interface ItemStudentsResponse {
  assessment_id: number;
  assessment_item_id: number;
  item_title: string;
  item_type: AssessmentItemType;
  class_group?: string | null;
  registered_count: number;
  // Server-sorted weakest-first; render in the order received.
  students: ItemStudentRow[];
}
