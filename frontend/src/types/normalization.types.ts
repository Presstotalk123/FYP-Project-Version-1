export interface NormalizationFD { lhs: string[]; rhs: string[] }
export interface NormalizationRelation { node_id: string; name: string; attributes: string[]; primary_key: string[] }
export interface NormalizationStep { step_id: string; parent_node_id: string; selected_fd: NormalizationFD; children: NormalizationRelation[] }
export interface NormalizationQuestion {
  id: number; version: string; title: string; difficulty: 'easy' | 'medium' | 'hard';
  scenario: string; relation_name: string; attributes: string[]; statements: { id: string; text: string }[];
  sample_rows: Record<string, string>[]; target_normal_form: '3NF' | 'BCNF';
  is_published: boolean; hide_correctness: boolean; semantic_judge_enabled: boolean; created_by: number; created_at: string;
}
export interface NormalizationAuthoring extends Omit<NormalizationQuestion, 'version'> {
  version: number; approved_fds: NormalizationFD[]; semantic_judge_enabled: boolean;
}
export type NormalizationQuestionInput = Omit<NormalizationAuthoring, 'id' | 'created_by' | 'created_at' | 'is_published'>;
export interface NormalizationPayload {
  exercise_id: string; exercise_version: string; target_normal_form: '3NF' | 'BCNF';
  functional_dependencies: NormalizationFD[]; assumption: string;
  relations: Omit<NormalizationRelation, 'node_id'>[];
  process: { workflow: 'recursive_decomposition'; root: NormalizationRelation; steps: NormalizationStep[] };
  canvas_positions: { node_id: string; x: number; y: number }[]; request_key: string;
}
export interface NormalizationResult {
  decision: 'accepted' | 'rejected' | 'staff_review';
  score: { fd_percent: number; normalization_percent: number; overall_percent: number };
  fd_evaluation: { decision: string; decision_source: string; feedback: string; formal_evidence: {
    logically_equivalent: boolean; sample_contradictions: { lhs: string[]; rhs: string[]; first_row: number; second_row: number }[];
  } };
  normalization_evaluation: {
    note: string;
    attribute_coverage: boolean; lossless_join: boolean; dependency_preservation: boolean;
    dependency_preservation_required: boolean; relations_satisfy_target: boolean; proposed_keys_correct: boolean;
    meets_requirements: boolean; missing_attributes: string[]; unpreserved_dependencies: string[];
    relation_results: { name: string; candidate_keys: string[][]; violations: string[] }[];
    process_evaluation: { valid: boolean; errors: string[]; step_results: { step: string; valid: boolean; feedback: string }[] };
  };
}
export interface NormalizationAttempt {
  id: string; question_id: number; user_id: number; question_version: number; created_at?: string;
  payload: NormalizationPayload; status: 'processing' | 'completed' | 'failed' | 'submitted';
  feedback_hidden: boolean; result: NormalizationResult | null; review_version: number;
  reviews: { id: number; actor_id: number; decision: string; reason: string; created_at: string }[];
  student_name?: string; student_email?: string; class_group?: string;
  snapshot?: NormalizationAuthoring;
}
export interface NormalizationProgress {
  question_id: number; attempt_count: number; best_score: number | null;
  completed: boolean; feedback_hidden: boolean; review_pending: boolean;
}
export interface NormalizationAnalytics {
  question: NormalizationQuestion; attempt_count: number; student_count: number; average_fd: number | null;
  average_normalization: number | null; average_score: number | null; review_pending: number;
  score_distribution: Record<string, number>; submissions: NormalizationAttempt[];
}
