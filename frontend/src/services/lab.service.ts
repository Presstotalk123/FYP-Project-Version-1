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
};
