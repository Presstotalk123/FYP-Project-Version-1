import api from '@/services/api.service';
import { RaExample, RaPlaygroundRunResponse, RaStatus } from '@/types/ra.types';

/** RA endpoints, relative to the shared API base URL (…/api/v1). */
export const RA_ENDPOINTS = {
  STATUS: '/ra/status',
  PLAYGROUND_EXAMPLES: '/ra/playground/examples',
  PLAYGROUND_RUN: '/ra/playground/run',
};

export const raQueryKeys = {
  status: ['ra', 'status'] as const,
  playgroundExamples: ['ra', 'playground', 'examples'] as const,
};

export const raService = {
  /** Whether the RA module is switched on (RA_ENABLED). Treats any failure as "off". */
  async getStatus(): Promise<RaStatus> {
    try {
      const response = await api.get<RaStatus>(RA_ENDPOINTS.STATUS);
      return response.data;
    } catch {
      return { enabled: false, aggregate_nulls: 'sql' };
    }
  },

  async getPlaygroundExamples(): Promise<RaExample[]> {
    const response = await api.get<RaExample[]>(RA_ENDPOINTS.PLAYGROUND_EXAMPLES);
    return response.data;
  },

  /** Load the schema (and data), then evaluate `expression` if given. Nothing is saved. */
  async runPlayground(schemaSql: string, dataSql: string, expression: string): Promise<RaPlaygroundRunResponse> {
    const response = await api.post<RaPlaygroundRunResponse>(RA_ENDPOINTS.PLAYGROUND_RUN, {
      schema_sql: schemaSql,
      data_sql: dataSql,
      expression,
    });
    return response.data;
  },
};
