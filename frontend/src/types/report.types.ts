import { AssessmentItemComponentScore } from '@/types/assessment.types';

// Practice-completion counts for the student Report page. Mirrors the backend
// StudentReportSummary schema (GET /student-report/summary). Assessment scores
// are not part of this — the report page reads those from the assessments list.
export interface StudentReportSummary {
  sql_questions_completed: number;
  erd_questions_completed: number;
  sql_labs_completed: number;
  graph_labs_completed: number;
}

// One submitted assessment in the staff per-student report: the student's own
// weighted score against the cohort average, plus the per-item breakdown.
export interface StudentReportAssessmentBlock {
  assessment_id: number;
  assessment_title: string;
  submitted_at: string | null;
  total_weighted_score: number | null;
  cohort_average: number | null;
  above_average: boolean | null;
  student_count: number;
  items: AssessmentItemComponentScore[];
}

// Staff-facing consolidated report for one student (GET /student-report/students/{id}).
export interface StudentFullReport {
  student_id: number;
  student_email: string;
  student_name: string | null;
  class_group: string | null;
  summary: StudentReportSummary;
  assessments: StudentReportAssessmentBlock[];
}
