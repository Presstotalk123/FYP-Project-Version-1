import { API_BASE_URL, API_ENDPOINTS } from "@/config/api.config";
import api from "./api.service";
import {
  ERDiagramQuestion,
  ERDiagramQuestionListItem,
  ERSubmissionRequest,
  ERSubmissionResponse,
  ERSubmissionStreamEvent,
  GenerateRubricRequest,
  GenerateRubricResponse,
  SaveERQuestionRequest,
} from "@/types/er-diagram.types";

const submissionUrl = `${API_BASE_URL}${API_ENDPOINTS.ER_DIAGRAM.SUBMISSION}`;

const parseErrorBody = async (response: Response): Promise<string> => {
  const text = await response.text();
  if (!text) {
    return `Request failed with status ${response.status}`;
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    // If upstream does not return JSON, fall back to raw text.
  }
  return text;
};

const parseSseBlock = (block: string): ERSubmissionStreamEvent | null => {
  const lines = block.split(/\r?\n/);
  let eventName = "";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (!eventName || dataLines.length === 0) return null;

  let payload: unknown = null;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }

  switch (eventName) {
    case "start":
    case "token":
    case "structured_output":
    case "done":
    case "error":
      return {
        event: eventName,
        data: payload,
      } as ERSubmissionStreamEvent;
    default:
      return null;
  }
};

const extractSseBlock = (buffer: string): { block: string; rest: string } | null => {
  const lf = buffer.indexOf("\n\n");
  const crlf = buffer.indexOf("\r\n\r\n");
  if (lf < 0 && crlf < 0) return null;

  if (lf >= 0 && (crlf < 0 || lf < crlf)) {
    return {
      block: buffer.slice(0, lf),
      rest: buffer.slice(lf + 2),
    };
  }

  return {
    block: buffer.slice(0, crlf),
    rest: buffer.slice(crlf + 4),
  };
};

export const erDiagramService = {
  async generateRubric(payload: GenerateRubricRequest): Promise<GenerateRubricResponse> {
    const formData = new FormData();

    formData.append("mode", payload.mode);
    formData.append("notation", payload.notation);
    formData.append("problem_title", payload.problem_title);
    formData.append("problem_statement", payload.problem_statement);

    if (payload.model_answer) {
      formData.append("model_answer", payload.model_answer);
    }

    if (payload.refinement_instruction?.trim()) {
      formData.append("refinement_instruction", payload.refinement_instruction.trim());
    }

    if (payload.rubric_previous) {
      formData.append("rubric_previous", JSON.stringify(payload.rubric_previous));
    }

    if (payload.instruction_history) {
      formData.append("instruction_history", JSON.stringify(payload.instruction_history));
    }

    const response = await api.post<GenerateRubricResponse>(API_ENDPOINTS.ER_DIAGRAM.GENERATE_RUBRIC, formData);
    return response.data;
  },

  async saveQuestion(payload: SaveERQuestionRequest): Promise<ERDiagramQuestion> {
    const formData = new FormData();
    formData.append("title", payload.title);
    formData.append("problem_statement", payload.problem_statement);
    formData.append("notation", payload.notation);
    formData.append("difficulty_label", payload.difficulty_label);
    formData.append("difficulty_rationale", payload.difficulty_rationale);
    formData.append("rubric_md", payload.rubric_md);
    formData.append("rubric_json", JSON.stringify(payload.rubric_json));
    formData.append("instruction_history", JSON.stringify(payload.instruction_history));

    if (payload.model_answer) {
      formData.append("model_answer", payload.model_answer);
    }

    const response = await api.post<ERDiagramQuestion>(API_ENDPOINTS.ER_DIAGRAM.QUESTIONS, formData);
    return response.data;
  },

  async getQuestions(): Promise<ERDiagramQuestionListItem[]> {
    const response = await api.get<ERDiagramQuestionListItem[]>(API_ENDPOINTS.ER_DIAGRAM.QUESTIONS);
    return response.data;
  },

  async getQuestionById(id: number): Promise<ERDiagramQuestion> {
    const response = await api.get<ERDiagramQuestion>(API_ENDPOINTS.ER_DIAGRAM.QUESTION_DETAIL(id));
    return response.data;
  },

  async deleteQuestion(id: number): Promise<void> {
    await api.delete(API_ENDPOINTS.ER_DIAGRAM.QUESTION_DETAIL(id));
  },

  async *submitStream(payload: ERSubmissionRequest): AsyncGenerator<ERSubmissionStreamEvent> {
    const formData = new FormData();
    formData.append("question_id", String(payload.question_id));
    formData.append("mode", payload.mode);
    if (payload.student_query?.trim()) {
      formData.append("student_query", payload.student_query.trim());
    }
    if (payload.submission_xml_text?.trim()) {
      formData.append("submission_xml_text", payload.submission_xml_text.trim());
    }
    if (payload.erd_img) {
      formData.append("erd_img", payload.erd_img);
    }

    const headers: HeadersInit = {};
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("access_token");
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
    }

    const response = await fetch(submissionUrl, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!response.ok) {
      const detail = await parseErrorBody(response);
      throw new Error(detail);
    }

    const contentType = (response.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("text/event-stream")) {
      const raw = await response.text();
      throw new Error(
        raw || `Submission stream protocol error. Expected text/event-stream, got '${contentType || "unknown"}'`,
      );
    }

    if (!response.body) {
      throw new Error("Submission stream is empty");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let hasDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      while (true) {
        const extracted = extractSseBlock(buffer);
        if (!extracted) break;
        const block = extracted.block.trim();
        buffer = extracted.rest;

        if (!block) continue;
        const event = parseSseBlock(block);
        if (!event) continue;

        yield event;
        if (event.event === "done") {
          hasDone = true;
        } else if (event.event === "error") {
          return;
        }
      }
    }

    if (buffer.trim()) {
      const trailingEvent = parseSseBlock(buffer.trim());
      if (trailingEvent) {
        yield trailingEvent;
        if (trailingEvent.event === "done") hasDone = true;
      }
    }

    if (!hasDone) {
      throw new Error("Submission stream interrupted before completion.");
    }
  },

  async submit(payload: ERSubmissionRequest): Promise<ERSubmissionResponse> {
    let result: ERSubmissionResponse | null = null;
    for await (const event of this.submitStream(payload)) {
      if (event.event === "done") {
        result = event.data as ERSubmissionResponse;
      }
      if (event.event === "error") {
        const errorData = event.data as { detail?: string };
        throw new Error(errorData.detail || "Submission stream failed");
      }
    }

    if (!result) {
      throw new Error("Submission stream interrupted before completion.");
    }

    return result;
  },
};