export type GenerateRubricMode = "create" | "patch";
export type ERSubmissionMode = "Query" | "Submit";
export type ERDifficultyLabel = "Easy" | "Medium" | "Hard";
export type RubricJsonPrimitive = string | number | boolean | null;
export type RubricJsonValue = RubricJsonPrimitive | RubricJsonObject | RubricJsonArray;
export interface RubricJsonObject {
  [key: string]: RubricJsonValue | undefined;
}
export type RubricJsonArray = RubricJsonValue[];
export type RubricFormSectionKey = "meta" | "policy" | "canonical_targets" | "checks";

export interface GenerateRubricDifficulty {
  label: ERDifficultyLabel;
  rationale: string;
}

export interface GenerateRubricClientInput {
  problem_title: string;
  problem_statement: string;
  model_answer?: File | null;
  refinement_instruction?: string;
}

export interface GenerateRubricRequest extends GenerateRubricClientInput {
  mode: GenerateRubricMode;
  notation: "Chen";
  rubric_previous?: ERRubricJson;
  instruction_history?: string[];
}

export interface GenerateRubricResponse {
  difficulty: GenerateRubricDifficulty;
  rubric_json: ERRubricJson;
  rubric_md: string;
  diff_summary: unknown[];
}

export interface SaveERQuestionRequest {
  title: string;
  problem_statement: string;
  notation: "Chen";
  difficulty_label: ERDifficultyLabel;
  difficulty_rationale: string;
  rubric_md: string;
  rubric_json: ERRubricJson;
  instruction_history: string[];
  show_rubric_on_attempt: boolean;
  model_answer?: File | null;
}

export type ERRubricCheckRequirementLevel =
  | "must"
  | "should"
  | "optional"
  | "not_applicable"
  | (string & {});

export interface ERRubricCheck extends RubricJsonObject {
  id: string;
  dimension: string;
  requirement_level: ERRubricCheckRequirementLevel;
  pass_criteria?: string;
  points?: number | null;
}

export type ERRubricJson = RubricJsonObject & {
  checks?: ERRubricCheck[];
};

export interface ERDiagramQuestion {
  id: number;
  title: string;
  problem_statement: string;
  notation: "Chen";
  difficulty_label: ERDifficultyLabel;
  difficulty_rationale: string;
  rubric_md?: string;
  rubric_json?: ERRubricJson;
  instruction_history: string[];
  show_rubric_on_attempt: boolean;
  model_answer_storage_key: string | null;
  model_answer_url: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
  /** Only sent to staff — how many students were graded on the current rubric. */
  attempt_count?: number;
}

export interface ERDiagramQuestionListItem {
  id: number;
  title: string;
  problem_statement: string;
  difficulty_label: ERDifficultyLabel;
  created_by: number;
  created_by_role: "student" | "staff" | "admin";
  created_at: string;
  is_published: boolean;
}

export interface ERSubmissionScore {
  label: string;
  earned_points: number;
  total_points: number;
  percent: number | string;
  [key: string]: unknown;
}

export type ERSubmissionCheckRequirementLevel = "must" | "should" | "optional" | "not_applicable";
export type ERSubmissionCheckStatus = "pass" | "fail" | "partial" | "not_applicable";

export interface ERSubmissionCheck {
  id: string;
  dimension: string;
  requirement_level: ERSubmissionCheckRequirementLevel;
  points: number;
  status: ERSubmissionCheckStatus;
  brief_reason: string;
}

export interface ERSubmissionStructuredOutput {
  score: ERSubmissionScore;
  student_message: string;
  checks: ERSubmissionCheck[];
}

export interface ERSubmissionRequest {
  question_id?: number;
  mode: ERSubmissionMode;
  student_query?: string | null;
  submission_xml_text?: string | null;
  submission_description?: string | null;
  erd_img?: File | null;
}

export interface ERSubmissionResponse {
  mode: ERSubmissionMode;
  text: string;
  structured_output: ERSubmissionStructuredOutput | null;
}

export interface ERSubmissionStreamStartEvent {
  event: "start";
  data: {
    mode: ERSubmissionMode;
    question_id: number;
  };
}

export interface ERSubmissionStreamTokenEvent {
  event: "token";
  data: {
    chunk: string;
    text: string;
  };
}

export interface ERSubmissionStreamStructuredOutputEvent {
  event: "structured_output";
  data: {
    structured_output: ERSubmissionStructuredOutput | null;
  };
}

export interface ERSubmissionStreamDoneEvent {
  event: "done";
  data: ERSubmissionResponse;
}

export interface ERSubmissionStreamErrorEvent {
  event: "error";
  data: {
    detail: string;
  };
}

export type ERSubmissionStreamEvent =
  | ERSubmissionStreamStartEvent
  | ERSubmissionStreamTokenEvent
  | ERSubmissionStreamStructuredOutputEvent
  | ERSubmissionStreamDoneEvent
  | ERSubmissionStreamErrorEvent;

export interface ErdTutorTranscriptMessage {
  id: number;
  role: "user" | "assistant" | "submission";
  mode: "query" | "submit";
  content: string | null;
  created_at: string | null;
}

export interface ErdTutorConversationResponse {
  exists: boolean;
  conversation_id: number | null;
  context_type: "standalone" | "lab" | null;
  ibl_stage: string | null;
  hint_level: number | null;
  last_submit_score: { percent?: number; label?: string } | null;
  last_submit_report?: ERSubmissionStructuredOutput | Record<string, unknown> | null;
  messages: ErdTutorTranscriptMessage[];
}
