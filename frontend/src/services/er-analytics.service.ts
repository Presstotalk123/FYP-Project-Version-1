import api from "./api.service";
import { API_BASE_URL, API_ENDPOINTS } from "@/config/api.config";
import type {
  AnalyticsContext,
  ClassOverview,
  QuestionAnalytics,
  ScoreOverrideResult,
  StudentSubmissions,
  SubmissionDetail,
} from "@/types/er-analytics.types";

export const erAnalyticsService = {
  async questionAnalytics(
    id: number,
    context: AnalyticsContext,
    classGroup?: string,
  ): Promise<QuestionAnalytics> {
    const r = await api.get<QuestionAnalytics>(API_ENDPOINTS.ER_ANALYTICS.QUESTION(id), {
      params: { context, ...(classGroup ? { class_group: classGroup } : {}) },
    });
    return r.data;
  },
  async classGroups(): Promise<string[]> {
    const r = await api.get<{ class_groups: string[] }>(API_ENDPOINTS.ER_ANALYTICS.CLASS_GROUPS);
    return r.data.class_groups;
  },
  async studentSubmissions(questionId: number, studentId: number): Promise<StudentSubmissions> {
    const r = await api.get<StudentSubmissions>(
      API_ENDPOINTS.ER_ANALYTICS.STUDENT(questionId, studentId),
    );
    return r.data;
  },
  async submissionDetail(submissionId: number): Promise<SubmissionDetail> {
    const r = await api.get<SubmissionDetail>(
      API_ENDPOINTS.ER_ANALYTICS.SUBMISSION(submissionId),
    );
    return r.data;
  },
  async overview(context: AnalyticsContext, classGroup?: string): Promise<ClassOverview> {
    const r = await api.get<ClassOverview>(API_ENDPOINTS.ER_ANALYTICS.OVERVIEW, {
      params: { context, ...(classGroup ? { class_group: classGroup } : {}) },
    });
    return r.data;
  },
};

/** Correct a graded attempt. `checks` maps check id -> points awarded, and carries
 *  only the ids being changed; the rest keep what the grader awarded. The server
 *  re-scores — the number the modal shows while editing is a preview, never what
 *  gets stored. */
export async function overrideSubmissionScore(
  submissionId: number,
  checks: Record<string, number>,
  reason: string,
): Promise<ScoreOverrideResult> {
  const r = await api.put<ScoreOverrideResult>(
    API_ENDPOINTS.ER_ANALYTICS.SUBMISSION_SCORE(submissionId),
    { checks, reason },
  );
  return r.data;
}

/** Restore the grader's original result and drop the correction. */
export async function revertSubmissionScore(submissionId: number): Promise<ScoreOverrideResult> {
  const r = await api.delete<ScoreOverrideResult>(
    API_ENDPOINTS.ER_ANALYTICS.SUBMISSION_SCORE(submissionId),
  );
  return r.data;
}

/** Direct URL for an <img> tag. The browser sends no Authorization header on
 * image loads, so pages fetch the image as a blob via `fetchSubmissionImage`
 * instead when auth is enforced; this helper builds the raw URL. */
export const submissionImageUrl = (submissionId: number): string =>
  `${API_BASE_URL}${API_ENDPOINTS.ER_ANALYTICS.SUBMISSION_IMAGE(submissionId)}`;

export async function fetchSubmissionImage(submissionId: number): Promise<string> {
  const r = await api.get<Blob>(API_ENDPOINTS.ER_ANALYTICS.SUBMISSION_IMAGE(submissionId), {
    responseType: "blob",
  });
  return URL.createObjectURL(r.data);
}

/** Where the diagram came from, echoed back so the UI can name it. */
export type AddedSubmissionSource = "draft" | "xml" | "image";

export interface StaffStudentDraft {
  exists: boolean;
  revision?: number;
  updated_at?: string | null;
  xml?: string;
}

/** A student's autosaved canvas, read as staff. The student-facing draft endpoint
 *  is scoped to the caller, so this is the only way in. */
export async function fetchStudentDraft(
  questionId: number,
  studentId: number,
): Promise<StaffStudentDraft> {
  const r = await api.get<StaffStudentDraft>(
    API_ENDPOINTS.ER_ANALYTICS.STUDENT_DRAFT(questionId, studentId),
  );
  return r.data;
}

export interface AddStudentSubmissionParams {
  questionId: number;
  studentId: number;
  reason: string;
  regrade?: boolean;
  /** Grade the student's own autosaved canvas. */
  useSavedDraft?: boolean;
  /** Contents of a .drawio or .xml file. */
  xmlText?: string;
  /** A PNG or JPG, read by the vision model. */
  imageFile?: File;
  /** A picture of the XML source, drawn by the browser. Stored, never graded, and
   *  optional: the attempt is graded with or without it. */
  renderedPng?: File | null;
}

export interface AddStudentSubmissionResult {
  submission_id: number;
  score: {
    label?: string;
    percent?: number;
    earned_points?: number;
    total_points?: number;
  };
  source: AddedSubmissionSource;
  added_by: string;
}

/** Grading runs 30-90 s, far longer than the shared axios default, which would
 * abort a perfectly healthy request part way through. */
const GRADING_TIMEOUT_MS = 180_000;

/**
 * Create a graded submission for a student, from a diagram staff supply.
 * Exactly one source must be given; the server rejects zero or two.
 */
export async function addStudentSubmission(
  params: AddStudentSubmissionParams,
): Promise<AddStudentSubmissionResult> {
  const form = new FormData();
  form.append("reason", params.reason);
  form.append("regrade", String(params.regrade ?? false));
  if (params.useSavedDraft) form.append("use_saved_draft", "true");
  if (params.xmlText) form.append("submission_xml_text", params.xmlText);
  if (params.imageFile) form.append("erd_img", params.imageFile);
  if (params.renderedPng) form.append("rendered_png", params.renderedPng);

  const r = await api.post<AddStudentSubmissionResult>(
    API_ENDPOINTS.ER_ANALYTICS.ADD_STUDENT_SUBMISSION(params.questionId, params.studentId),
    form,
    { timeout: GRADING_TIMEOUT_MS },
  );
  return r.data;
}
