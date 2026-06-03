import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import type {
  ErLabResponse, ErLabStaffDetail, ErLabQuestionResponse,
  ErLabSessionResponse, ErLabSubmissionResponse, ErLabMyScoresResponse,
  ErLabStudentsResponse,
} from '@/types/er-lab.types';

const E = API_ENDPOINTS.ER_LABS;

export const erLabsService = {
  list: () => api.get<ErLabResponse[]>(E.BASE).then(r => r.data),
  create: (body: { title: string; description: string; join_password: string }) =>
    api.post<ErLabStaffDetail>(E.BASE, body).then(r => r.data),
  get: (id: number) => api.get<ErLabStaffDetail | ErLabResponse>(E.DETAIL(id)).then(r => r.data),
  update: (id: number, body: Partial<{ title: string; description: string; join_password: string }>) =>
    api.put<ErLabResponse>(E.DETAIL(id), body).then(r => r.data),
  remove: (id: number) => api.delete(E.DETAIL(id)),
  publish: (id: number) => api.post<ErLabResponse>(E.PUBLISH(id)).then(r => r.data),
  unpublish: (id: number) => api.post<ErLabResponse>(E.UNPUBLISH(id)).then(r => r.data),
  start: (id: number) => api.post<ErLabResponse>(E.START(id)).then(r => r.data),
  stop: (id: number) => api.post(E.STOP(id)).then(r => r.data),

  listQuestions: (id: number) => api.get<ErLabQuestionResponse[]>(E.QUESTIONS(id)).then(r => r.data),
  createQuestion: (id: number, formData: FormData) =>
    api.post<ErLabQuestionResponse>(E.QUESTIONS(id), formData).then(r => r.data),
  getQuestion: (id: number, qid: number) =>
    api.get<ErLabQuestionResponse>(E.QUESTION_DETAIL(id, qid)).then(r => r.data),
  updateQuestion: (id: number, qid: number, formData: FormData) =>
    api.put<ErLabQuestionResponse>(E.QUESTION_DETAIL(id, qid), formData).then(r => r.data),
  deleteQuestion: (id: number, qid: number) => api.delete(E.QUESTION_DETAIL(id, qid)),

  startSession: (id: number, join_password: string) =>
    api.post<ErLabSessionResponse>(E.SESSION_START(id), { join_password }).then(r => r.data),
  getSession: (id: number) => api.get<ErLabSessionResponse>(E.SESSION_GET(id)).then(r => r.data),
  exitSession: (id: number) => api.post(E.SESSION_EXIT(id)).then(r => r.data),

  mySubmissions: (id: number, studentId?: number) =>
    api.get<ErLabSubmissionResponse[]>(E.MY_SUBMISSIONS(id),
      { params: studentId ? { student_id: studentId } : {} }).then(r => r.data),
  myScores: (id: number, studentId?: number) =>
    api.get<ErLabMyScoresResponse>(E.MY_SCORES(id),
      { params: studentId ? { student_id: studentId } : {} }).then(r => r.data),
  students: (id: number) => api.get<ErLabStudentsResponse>(E.STUDENTS(id)).then(r => r.data),

  setOverride: (subId: number, body: { score_earned: number; score_total: number; reason: string }) =>
    api.post<ErLabSubmissionResponse>(E.SUBMISSION_OVERRIDE(subId), body).then(r => r.data),
  clearOverride: (subId: number) =>
    api.delete<ErLabSubmissionResponse>(E.SUBMISSION_OVERRIDE(subId)).then(r => r.data),
};
