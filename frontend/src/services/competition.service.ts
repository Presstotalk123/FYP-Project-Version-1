import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import type { AdminCompetition, AdminIncident, CompetitionDetail, CompetitionSource, CompetitionSummary, IncidentDocument, IncidentListItem, IncidentReport, IncidentVersion, ParticipantRow, PublicIncident, QueryOutput, RepairFeedback, StaffSubmission, SubmissionResult, ValidationReport } from '@/types/competition.types';

const paths = API_ENDPOINTS.COMPETITION;
const item = (id: number, key: string) => `${paths.SESSIONS}/${id}/items/${encodeURIComponent(key)}`;
export const competitionService = {
  capabilities: async () => (await api.get<{ enabled: boolean }>(`${paths.BASE}/capabilities`)).data,
  list: async () => (await api.get<CompetitionSummary[]>(paths.BASE)).data,
  detail: async (id: number) => (await api.get<CompetitionDetail>(`${paths.BASE}/${id}`)).data,
  join: async (id: number) => (await api.post<{ participation_id: number }>(`${paths.BASE}/${id}/join`)).data,
  incident: async (id: number, key: string) => (await api.get<PublicIncident>(item(id, key))).data,
  save: async (id: number, key: string, revision: number, report: IncidentReport) => (await api.put<{ revision: number; report: IncidentReport }>(`${item(id, key)}/draft`, { revision, report })).data,
  run: async (id: number, key: string, query: string, component_id?: string) => (await api.post<QueryOutput & { run_id: number }>(`${item(id, key)}/runs`, { query, component_id })).data,
  check: async (id: number, key: string, query: string, component_id: string) => (await api.post<RepairFeedback>(`${item(id, key)}/checks`, { query, component_id })).data,
  help: async (id: number, key: string) => (await api.post<{ level: number; checkpoints: string[] }>(`${item(id, key)}/help`)).data,
  inspect: async (id: number, key: string, artifact_type: 'component' | 'table', artifact_id: string) => (await api.post(`${item(id, key)}/inspections`, { artifact_type, artifact_id })).data,
  survey: async (id: number, usability: number, engagement: number, feedback: string) => (await api.post(`${paths.SESSIONS}/${id}/survey`, { usability, engagement, feedback })).data,
  submit: async (id: number, key: string, revision: number, request_key: string) => (await api.post<SubmissionResult>(`${item(id, key)}/submissions`, { revision, request_key })).data,
  adminList: async () => (await api.get<AdminCompetition[]>(paths.ADMIN)).data,
  adminDetail: async (id: number) => (await api.get<AdminCompetition>(`${paths.ADMIN}/${id}`)).data,
  saveCompetition: async (body: Omit<AdminCompetition, 'id' | 'published' | 'content_hash'>, id?: number) => (await (id ? api.put<AdminCompetition>(`${paths.ADMIN}/${id}`, body) : api.post<AdminCompetition>(paths.ADMIN, body))).data,
  publish: async (id: number) => (await api.post<AdminCompetition>(`${paths.ADMIN}/${id}/publish`)).data,
  window: async (id: number, opens_at: string | null, closes_at: string | null) => (await api.put<AdminCompetition>(`${paths.ADMIN}/${id}/window`, { opens_at, closes_at })).data,
  sources: async () => (await api.get<CompetitionSource[]>(paths.SOURCES)).data,
  source: async (id: number) => (await api.get<CompetitionSource>(`${paths.SOURCES}/${id}`)).data,
  importSources: async (entries: Record<string, unknown>[], authorised: boolean) => (await api.post<CompetitionSource[]>(`${paths.SOURCES}/import`, { entries, authorised }, { timeout: 180000 })).data,
  importQuestion: async (id: number) => (await api.post<CompetitionSource>(`${paths.SOURCES}/from-question/${id}`)).data,
  authorise: async (id: number) => (await api.post(`${paths.SOURCES}/${id}/authorise`)).data,
  adapt: async (id: number, template: string, complaint: string, business_rules: string) => (await api.post<{ id: number }>(`${paths.SOURCES}/${id}/adapt`, { template, complaint, business_rules })).data,
  incidents: async () => (await api.get<IncidentListItem[]>(paths.INCIDENTS)).data,
  adminIncident: async (id: number) => (await api.get<AdminIncident>(`${paths.INCIDENTS}/${id}`)).data,
  saveIncident: async (document: IncidentDocument, source_id: number | null, id?: number, revision?: number) => (await (id ? api.put<AdminIncident>(`${paths.INCIDENTS}/${id}`, { document, source_id, revision }) : api.post<AdminIncident>(paths.INCIDENTS, { document, source_id }))).data,
  validate: async (id: number) => (await api.post<ValidationReport>(`${paths.INCIDENTS}/${id}/validate`, {}, { timeout: 30000 })).data,
  approve: async (id: number) => (await api.post<{ version_id: number }>(`${paths.INCIDENTS}/${id}/approve`)).data,
  versions: async () => (await api.get<IncidentVersion[]>(paths.VERSIONS)).data,
  preview: async (id: number) => (await api.get<{ complaint: string; business_rules: string; features: { label: string; faulty: QueryOutput; reference: QueryOutput }[] }>(`${paths.INCIDENTS}/${id}/preview`)).data,
  participants: async (id: number) => (await api.get<ParticipantRow[]>(`${paths.ADMIN}/${id}/participants`)).data,
  submissions: async (id: number) => (await api.get<StaffSubmission[]>(`${paths.ADMIN}/${id}/submissions`)).data,
  review: async (id: number, diagnosis_score: number, explanation_score: number, rationale: string) => (await api.post(`/admin/competition-submissions/${id}/reviews`, { diagnosis_score, explanation_score, rationale })).data,
  retryJudgement: async (id: number) => (await api.post(`/admin/competition-submissions/${id}/retry`)).data,
  export: async (id: number, mode: string) => {
    const response = await api.get<Blob>(`${paths.ADMIN}/${id}/exports/${mode}`, { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a'); link.href = url; link.download = `competition-${id}-${mode}.csv`; link.click(); URL.revokeObjectURL(url);
  },
};
