import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import {
  Lab,
  LabDetail,
  LabCreate,
  LabUpdate,
  LabSession,
  SessionStartResponse,
  LabExecuteRequest,
  LabExecuteResponse,
  SchemaPreview,
  StopLabResponse,
  LabAttemptResponse,
  LabQueryHistoryResponse,
  LabTask,
  LabTaskCreate,
  LabTaskAssignAnswer,
  LabTaskUpdate,
  LabTaskValidateRequest,
  LabTaskValidateResponse,
  LabTaskSubmitRequest,
  LabTaskSubmitResponse,
  LabTaskProgressResponse,
  LabStudentAttemptsResponse,
} from '@/types/lab.types';

export const labService = {
  // ============================================================================
  // Staff - Lab Management
  // ============================================================================

  async createLab(data: LabCreate): Promise<Lab> {
    const response = await api.post(API_ENDPOINTS.LABS.BASE, data);
    return response.data;
  },

  async getLabs(): Promise<Lab[]> {
    const response = await api.get(API_ENDPOINTS.LABS.BASE);
    return response.data;
  },

  async getLabById(id: number): Promise<LabDetail> {
    const response = await api.get(API_ENDPOINTS.LABS.DETAIL(id));
    return response.data;
  },

  async updateLab(id: number, data: LabUpdate): Promise<Lab> {
    const response = await api.put(API_ENDPOINTS.LABS.DETAIL(id), data);
    return response.data;
  },

  async deleteLab(id: number): Promise<void> {
    await api.delete(API_ENDPOINTS.LABS.DETAIL(id));
  },

  // ============================================================================
  // Staff - State Management
  // ============================================================================

  async publishLab(id: number): Promise<Lab> {
    const response = await api.post(API_ENDPOINTS.LABS.PUBLISH(id));
    return response.data;
  },

  async unpublishLab(id: number): Promise<Lab> {
    const response = await api.post(API_ENDPOINTS.LABS.UNPUBLISH(id));
    return response.data;
  },

  async startLab(id: number): Promise<Lab> {
    const response = await api.post(API_ENDPOINTS.LABS.START(id));
    return response.data;
  },

  async stopLab(id: number): Promise<StopLabResponse> {
    const response = await api.post(API_ENDPOINTS.LABS.STOP(id));
    return response.data;
  },

  // ============================================================================
  // Student - Session Management
  // ============================================================================

  async startSession(labId: number): Promise<SessionStartResponse> {
    const response = await api.post(API_ENDPOINTS.LABS.SESSION_START(labId));
    return response.data;
  },

  async getActiveSession(labId: number): Promise<LabSession> {
    const response = await api.get(API_ENDPOINTS.LABS.SESSION_GET(labId));
    return response.data;
  },

  async executeQuery(
    sessionId: number,
    query: string
  ): Promise<LabExecuteResponse> {
    const response = await api.post(
      API_ENDPOINTS.LABS.SESSION_EXECUTE(sessionId),
      { query } as LabExecuteRequest
    );
    return response.data;
  },

  async exitSession(labId: number): Promise<void> {
    await api.post(API_ENDPOINTS.LABS.SESSION_EXIT(labId));
  },

  async getSessionAttempts(sessionId: number): Promise<LabAttemptResponse[]> {
    const response = await api.get(API_ENDPOINTS.LABS.SESSION_ATTEMPTS(sessionId));
    return response.data;
  },

  async getLabHistory(labId: number): Promise<LabQueryHistoryResponse[]> {
    const response = await api.get(API_ENDPOINTS.LABS.LAB_HISTORY(labId));
    return response.data;
  },

  async getAllLabsHistory(): Promise<LabQueryHistoryResponse[]> {
    const response = await api.get(API_ENDPOINTS.LABS.ALL_HISTORY);
    return response.data;
  },

  async resetSession(labId: number): Promise<void> {
    await api.post(API_ENDPOINTS.LABS.SESSION_RESET(labId));
  },

  async getDatabaseState(sessionId: number): Promise<any> {
    const response = await api.get(API_ENDPOINTS.LABS.SESSION_DATABASE(sessionId));
    return response.data;
  },

  // ============================================================================
  // Preview
  // ============================================================================

  async getSchemaPreview(labId: number): Promise<SchemaPreview> {
    const response = await api.get(API_ENDPOINTS.LABS.PREVIEW(labId));
    return response.data;
  },

  // ============================================================================
  // Task Management
  // ============================================================================

  async getLabTasks(labId: number): Promise<LabTask[]> {
    const response = await api.get(API_ENDPOINTS.LABS.TASKS(labId));
    return response.data;
  },

  async createLabTask(labId: number, data: LabTaskCreate): Promise<LabTask> {
    const response = await api.post(API_ENDPOINTS.LABS.TASKS(labId), data);
    return response.data;
  },

  async assignTaskAnswer(
    labId: number,
    taskId: number,
    data: LabTaskAssignAnswer
  ): Promise<LabTask> {
    const response = await api.post(
      API_ENDPOINTS.LABS.TASK_ASSIGN(labId, taskId),
      data
    );
    return response.data;
  },

  async updateLabTask(
    labId: number,
    taskId: number,
    data: LabTaskUpdate
  ): Promise<LabTask> {
    const response = await api.put(
      API_ENDPOINTS.LABS.TASK_DETAIL(labId, taskId),
      data
    );
    return response.data;
  },

  async deleteLabTask(labId: number, taskId: number): Promise<void> {
    await api.delete(API_ENDPOINTS.LABS.TASK_DETAIL(labId, taskId));
  },

  async validateTaskAnswer(
    data: LabTaskValidateRequest
  ): Promise<LabTaskValidateResponse> {
    const response = await api.post(API_ENDPOINTS.LABS.TASK_VALIDATE, data);
    return response.data;
  },

  async submitTaskAnswer(
    data: LabTaskSubmitRequest
  ): Promise<LabTaskSubmitResponse> {
    const response = await api.post(API_ENDPOINTS.LABS.TASK_SUBMIT, data);
    return response.data;
  },

  async getLabTaskProgress(labId: number): Promise<LabTaskProgressResponse> {
    const response = await api.get(API_ENDPOINTS.LABS.TASK_PROGRESS(labId));
    return response.data;
  },

  async getStudentAttempts(
    labId: number
  ): Promise<LabStudentAttemptsResponse> {
    const response = await api.get(API_ENDPOINTS.LABS.STUDENT_ATTEMPTS(labId));
    return response.data;
  },
};
