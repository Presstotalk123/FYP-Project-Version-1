export type LabItemKind = 'sql' | 'erd' | 'sqllab';

export interface LabItem {
  id: number;
  kind: LabItemKind;
  ref_id: number | null;
  order_index: number;
  title: string;
  difficulty: string | null;
}

export interface UnifiedLabDetail {
  id: number;
  title: string;
  description: string;
  is_published: boolean;
  is_running: boolean;
  items: LabItem[];
}

export interface UnifiedLabListItem {
  id: number;
  title: string;
  description: string;
  is_published: boolean;
  is_running: boolean;
  created_at: string;
  updated_at: string;
}

export interface UnifiedLabCreate {
  title: string;
  description: string;
  join_password: string;
}

export interface UnifiedLabCreateResponse {
  id: number;
  title: string;
  join_password: string;
}

export interface LabItemProgress {
  lab_item_id: number;
  kind: LabItemKind;
  lab_task_id: number | null;
  is_passed: boolean;
  score_percent: number | null;
}

export interface LabProgress {
  lab_id: number;
  done: number;
  total: number;
  items: LabItemProgress[];
}

export interface ItemGradeResult {
  is_passed: boolean;
  score_earned: number | null;
  score_total: number | null;
  message: string;
}

export interface DatabaseColumn {
  name: string;
  type: string;
}

export interface DatabaseTableState {
  name: string;
  columns: DatabaseColumn[];
  row_count: number;
  sample_rows: Array<Record<string, unknown>>;
}

export interface DatabaseState {
  tables: DatabaseTableState[];
}

export interface LabSessionResponse {
  id: number;
  lab_id: number;
  user_id: number;
  is_active: boolean;
  started_at: string;
}

export interface UnifiedLabStudent {
  user_id: number;
  email: string;
  passed_items: number;
  total_items: number;
  last_submitted_at: string | null;
}

export interface UnifiedLabStudentsResponse {
  lab_id: number;
  total_items: number;
  students: UnifiedLabStudent[];
}

export interface SqlLabItemTask {
  id: number;
  title: string;
  description: string;
  order_index: number;
}

export interface SqlLabRunResult {
  success: boolean;
  columns: string[];
  results: Array<Record<string, unknown>>;
  row_count: number;
  error_message: string | null;
}

export interface UnifiedLabSubmissionView {
  id: number;
  lab_item_id: number;
  kind: string;
  item_title: string;
  is_passed: boolean;
  score_earned: number | null;
  score_total: number | null;
  override_score_earned: number | null;
  override_score_total: number | null;
  submitted_at: string;
}
