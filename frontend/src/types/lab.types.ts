export interface Lab {
  id: number;
  title: string;
  description: string;
  is_published: boolean;
  is_running: boolean;
  created_at: string;
  updated_at: string;
}

export interface LabDetail extends Lab {
  template_db_path: string;
  schema_sql: string;
  sample_data_sql: string;
  created_by: number;
}

export interface LabSession {
  id: number;
  lab_id: number;
  user_id: number;
  is_active: boolean;
  started_at: string;
  ended_at: string | null;
}

export interface LabCreate {
  title: string;
  description: string;
  schema_sql: string;
  sample_data_sql: string;
}

export interface LabUpdate {
  title?: string;
  description?: string;
  schema_sql?: string;
  sample_data_sql?: string;
}

export interface SessionStartResponse {
  session_id: number;
  lab_id: number;
  started_at: string;
}

export interface LabExecuteRequest {
  query: string;
}

export interface LabExecuteResponse {
  success: boolean;
  columns: string[];
  results: any[];
  execution_time_ms: number;
  row_count: number;
  error_message: string | null;
}

export interface ColumnInfo {
  name: string;
  type: string;
  notnull: boolean;
  default_value: string | null;
  pk: boolean;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
  create_sql: string;
}

export interface SchemaPreview {
  tables: TableInfo[];
}

export interface StopLabResponse {
  message: string;
  sessions_terminated: number;
}

export interface LabAttemptResponse {
  id: number;
  query: string;
  success: boolean;
  execution_time_ms: number;
  row_count: number;
  error_message: string | null;
  submitted_at: string;
}

export interface TableSampleData {
  columns: string[];
  rows: Record<string, any>[];
}

export interface TableState {
  name: string;
  columns: ColumnInfo[];
  create_sql: string;
  row_count: number;
  sample_data: TableSampleData;
}

export interface DatabaseState {
  tables: TableState[];
}
