import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import {
  ConceptGraph,
  PeerBenchmark,
  ScaffoldingState,
  Concept,
  QuestionConceptTag,
} from '@/types/lad.types';

export const ladService = {
  // Student-facing reads
  async getConceptGraph(): Promise<ConceptGraph> {
    const res = await api.get<ConceptGraph>(API_ENDPOINTS.LAD.CONCEPT_GRAPH);
    return res.data;
  },

  async getPeerBenchmark(): Promise<PeerBenchmark> {
    const res = await api.get<PeerBenchmark>(API_ENDPOINTS.LAD.PEER_BENCHMARK);
    return res.data;
  },

  async getScaffolding(questionId: number): Promise<ScaffoldingState> {
    const res = await api.get<ScaffoldingState>(API_ENDPOINTS.LAD.SCAFFOLDING(questionId));
    return res.data;
  },

  // Concept taxonomy + question tagging (staff)
  async listConcepts(): Promise<Concept[]> {
    const res = await api.get<Concept[]>(API_ENDPOINTS.LAD.CONCEPTS);
    return res.data;
  },

  async getQuestionConcepts(questionId: number): Promise<QuestionConceptTag[]> {
    const res = await api.get<QuestionConceptTag[]>(
      API_ENDPOINTS.LAD.QUESTION_CONCEPTS(questionId),
    );
    return res.data;
  },

  async setQuestionConcepts(
    questionId: number,
    tags: QuestionConceptTag[],
  ): Promise<QuestionConceptTag[]> {
    const res = await api.put<QuestionConceptTag[]>(
      API_ENDPOINTS.LAD.QUESTION_CONCEPTS(questionId),
      { tags },
    );
    return res.data;
  },
};
