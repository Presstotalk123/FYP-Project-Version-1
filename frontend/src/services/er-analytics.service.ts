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
