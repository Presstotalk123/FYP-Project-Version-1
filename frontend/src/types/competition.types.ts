export type CompetitionPhase = 'gameplay' | 'complete';
export type Cell = string | number | boolean | null;
export interface QueryOutput { success?: boolean; columns: string[]; rows: Cell[][]; error?: string | null; truncated?: boolean; execution_time_ms?: number; run_id?: number; }
export interface IncidentComponent { id: string; label: string; purpose: string; query: string; }
export interface IncidentReport { verdict: '' | 'correct' | 'incorrect'; investigation_sql: string; component_id: string; evidence: string; diagnosis: string; repair_sql: string; explanation: string; run_id: number | null; }
export interface IncidentDraft { revision: number; report: Partial<IncidentReport>; submitted: boolean; }
export interface PublicIncident {
  title: string; topic: string; difficulty: string; complaint: string; business_rules: string; schema_sql: string;
  report_style: 'investigation' | 'verdict'; points: number;
  components: IncidentComponent[]; features: { component_id: string; label: string; output: QueryOutput }[];
  database: { name: string; columns: { name: string; type: string; primary_key: boolean }[]; rows: Cell[][] }[];
  draft: IncidentDraft; assistance_allowed: boolean; checkpoints: string[]; checkpoint_count: number; read_only: boolean;
  runs: { id: number; sql: string; result: QueryOutput }[];
}
export interface CompetitionItem { key: string; title: string; difficulty: string; points: number; submitted: boolean; restored?: boolean; }
export interface Participation {
  id: number; competition_id: number; phase: CompetitionPhase;
  participation_complete: boolean; points: number; badges: string[]; items: CompetitionItem[];
}
export interface Leaderboard { enabled: boolean; updated_at: string; rows: { alias: string; points: number; elapsed_seconds: number | null; rank: number; is_you: boolean }[]; }
export interface CompetitionSummary { id: number; title: string; description: string; topic: string; opens_at: string | null; closes_at: string | null; open: boolean; mission_count: number; participation_id?: number | null; phase?: CompetitionPhase | null; time_tiebreak: boolean; }
export interface CompetitionDetail extends CompetitionSummary { participation: Participation | null; leaderboard: Leaderboard; }
export interface RepairFeedback { restored: boolean; passed_checks: number; total_checks: number; verdict_correct?: boolean; }
export interface SubmissionResult { id: number; status: string; submitted: boolean; feedback: RepairFeedback | null; }
export interface IncidentDocument {
  title: string; topic: string; difficulty: 'easy' | 'medium' | 'hard'; complaint: string; business_rules: string; schema_sql: string;
  report_style?: 'investigation' | 'verdict';
  components: (IncidentComponent & { reference_query: string; order_sensitive?: boolean; numeric_tolerance?: number })[];
  culprit_component: string; fault_template: string; fault_cause: string; checkpoints: string[];
  scenarios: { id: string; label: string; visible: boolean; seed_sql: string; approved_outputs: Record<string, QueryOutput> }[];
  oracle_confirmed: boolean; alternative_repairs?: string[];
}
export interface ValidationReport { valid: boolean; errors: string[]; cases: { scenario: string; component: string; reference_ok: boolean; fault_executes: boolean; matches_approved: boolean; actual: QueryOutput; approved: QueryOutput }[]; content_hash: string; parser_version: string; }
export interface AdminIncident { id: number; title: string; source_id: number | null; status: string; revision: number; document: IncidentDocument; validation: ValidationReport | null; }
export interface IncidentListItem { id: number; title: string; status: string; difficulty: string; topic: string; }
export interface IncidentVersion { id: number; incident_id: number; title: string; topic: string; difficulty: string; content_hash: string; }
export interface CompetitionConfig { missions: number[]; class_groups: string[]; leaderboard: boolean; points: Record<string, number>; time_tiebreak: boolean; }
export interface AdminCompetition { id: number; title: string; description: string; topic: string; config: CompetitionConfig; published: boolean; opens_at: string | null; closes_at: string | null; content_hash: string | null; }
export interface CompetitionSource { id: number; provider: string; external_id: string; title: string; eligible: boolean; authorised: boolean; diagnostics: string[]; content_hash: string; snapshot?: Record<string, unknown>; }
export interface RubricReview { diagnosis_score: number; explanation_score: number; rationale: string; reviewer_id: number; created_at: string; }
export interface StaffSubmission { id: number; item: string; name: string; cohort: string; payload: IncidentReport; status: string; result: (RepairFeedback & { diagnosis_location_correct?: boolean }) | null; help_level: number; fault_cause: string; reference_query: string; reviews: RubricReview[]; }
export interface ParticipantRow extends Participation { name: string | null; email: string; cohort: string; }
