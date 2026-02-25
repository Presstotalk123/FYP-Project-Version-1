export type GenerateRubricMode = "create" | "patch";
export type ERSubmissionMode = "Query" | "Submit";
export type ERDifficultyLabel = "Easy" | "Medium" | "Hard";

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
  rubric_previous?: Record<string, unknown>;
  instruction_history?: string[];
}

export interface GenerateRubricResponse {
  difficulty: GenerateRubricDifficulty;
  rubric_json: Record<string, unknown>;
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
  rubric_json: Record<string, unknown>;
  instruction_history: string[];
  model_answer?: File | null;
}

export interface ERDiagramQuestion {
  id: number;
  title: string;
  problem_statement: string;
  notation: "Chen";
  difficulty_label: ERDifficultyLabel;
  difficulty_rationale: string;
  rubric_md: string;
  rubric_json: Record<string, unknown>;
  instruction_history: string[];
  model_answer_storage_key: string | null;
  model_answer_url: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface ERDiagramQuestionListItem {
  id: number;
  title: string;
  problem_statement: string;
  difficulty_label: ERDifficultyLabel;
  created_at: string;
}

export interface ERSubmissionRequest {
  question_id: number;
  mode: ERSubmissionMode;
  student_query?: string;
  submission_xml_text?: string;
  erd_img?: File | null;
}

export interface ERSubmissionResponse {
  mode: ERSubmissionMode;
  text: string;
  structured_output: Record<string, unknown> | null;
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
    structured_output: Record<string, unknown> | null;
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