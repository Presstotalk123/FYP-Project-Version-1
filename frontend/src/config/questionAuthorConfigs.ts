import { QuestionAuthorConfig } from '@/types/question-author.types';
import { sqlLabAuthoring } from '@/services/sqlLabQuestion.service';
import { graphAuthoring } from '@/services/graphQuestion.service';

export const sqlLabAuthorConfig: QuestionAuthorConfig = {
  editorLanguage: 'sql',
  seedFields: [
    { key: 'schema_sql', label: 'Schema SQL', language: 'sql' },
    { key: 'sample_data_sql', label: 'Seed data SQL', language: 'sql' },
  ],
  service: sqlLabAuthoring,
  poolHref: '/problems',
  createDraft: (meta, seed) => sqlLabAuthoring.createDraft(meta, seed),
  newAuthorHref: (id) => `/sql-lab/${id}/author`,
};

export const graphAuthorConfig: QuestionAuthorConfig = {
  editorLanguage: 'cypher',
  seedFields: [{ key: 'seed_cypher', label: 'Seed graph (Cypher)', language: 'cypher' }],
  service: graphAuthoring,
  poolHref: '/problems',
  createDraft: (meta, seed) => graphAuthoring.createDraft(meta, seed),
  newAuthorHref: (id) => `/graph-lab/${id}/author`,
};
