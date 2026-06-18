import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import {
  DatabaseState, ItemGradeResult, LabItem, LabItemKind, LabProgress,
  LabSessionResponse, SqlLabItemTask, SqlLabRunResult,
  UnifiedLabCreate, UnifiedLabCreateResponse, UnifiedLabDetail, UnifiedLabListItem,
  UnifiedLabStudentsResponse, UnifiedLabSubmissionView,
} from '@/types/unified-lab.types';

const E = API_ENDPOINTS.UNIFIED_LABS;

export const unifiedLabService = {
  async create(payload: UnifiedLabCreate): Promise<UnifiedLabCreateResponse> {
    return (await api.post<UnifiedLabCreateResponse>(E.BASE, payload)).data;
  },
  async list(): Promise<UnifiedLabListItem[]> {
    return (await api.get<UnifiedLabListItem[]>(E.BASE)).data;
  },
  async get(id: number): Promise<UnifiedLabDetail> {
    return (await api.get<UnifiedLabDetail>(E.DETAIL(id))).data;
  },
  async addItem(id: number, kind: LabItemKind, ref_id: number | null): Promise<LabItem> {
    return (await api.post<LabItem>(E.ITEMS(id), { kind, ref_id })).data;
  },
  async removeItem(id: number, itemId: number): Promise<void> {
    await api.delete(E.ITEM(id, itemId));
  },
  async reorder(id: number, itemIds: number[]): Promise<void> {
    await api.put(E.ITEMS_ORDER(id), { item_ids: itemIds });
  },
  async startSession(id: number, joinPassword?: string): Promise<LabSessionResponse> {
    return (await api.post<LabSessionResponse>(E.SESSION_START(id), { join_password: joinPassword })).data;
  },
  async submitItem(id: number, itemId: number, query: string, labTaskId?: number): Promise<ItemGradeResult> {
    return (await api.post<ItemGradeResult>(E.ITEM_SUBMIT(id, itemId), { query, lab_task_id: labTaskId ?? null })).data;
  },
  async itemTasks(id: number, itemId: number): Promise<SqlLabItemTask[]> {
    return (await api.get<SqlLabItemTask[]>(E.ITEM_TASKS(id, itemId))).data;
  },
  async itemRun(id: number, itemId: number, query: string): Promise<SqlLabRunResult> {
    return (await api.post<SqlLabRunResult>(E.ITEM_RUN(id, itemId), { query })).data;
  },
  async itemDatabase(id: number, itemId: number): Promise<DatabaseState> {
    return (await api.get<DatabaseState>(E.ITEM_DATABASE(id, itemId))).data;
  },
  async itemReset(id: number, itemId: number): Promise<void> {
    await api.post(E.ITEM_RESET(id, itemId));
  },
  async progress(id: number): Promise<LabProgress> {
    return (await api.get<LabProgress>(E.PROGRESS(id))).data;
  },
  async publish(id: number) { await api.post(E.PUBLISH(id)); },
  async unpublish(id: number) { await api.post(E.UNPUBLISH(id)); },
  async start(id: number) { await api.post(E.START(id)); },
  async stop(id: number) { await api.post(E.STOP(id)); },
  async students(id: number): Promise<UnifiedLabStudentsResponse> {
    return (await api.get<UnifiedLabStudentsResponse>(E.STUDENTS(id))).data;
  },
  async submissions(id: number, studentId?: number): Promise<UnifiedLabSubmissionView[]> {
    return (await api.get<UnifiedLabSubmissionView[]>(E.SUBMISSIONS(id), { params: { student_id: studentId } })).data;
  },
  async override(subId: number, payload: { score_earned: number; score_total: number; reason?: string }): Promise<ItemGradeResult> {
    return (await api.post<ItemGradeResult>(E.OVERRIDE(subId), payload)).data;
  },
};
