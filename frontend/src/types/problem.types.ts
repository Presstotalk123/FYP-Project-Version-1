export type ProblemType = 'sql' | 'erd';
export type ProblemDifficulty = 'easy' | 'medium' | 'hard';
export type ProblemCreatorRole = 'student' | 'staff';
export type ProblemAuthorFilter = 'all' | 'staff' | 'students';

export interface ProblemListItem {
  type: ProblemType;
  id: number;
  title: string;
  difficulty: ProblemDifficulty;
  created_by: number;
  created_by_role: ProblemCreatorRole;
  created_at: string;
}

export interface ProblemCounts {
  all: number;
  sql: number;
  erd: number;
}

export interface ProblemListResponse {
  items: ProblemListItem[];
  counts: ProblemCounts;
}

export interface ProblemQueryParams {
  type?: ProblemType;
  difficulty?: ProblemDifficulty;
  search?: string;
  author?: ProblemAuthorFilter;
}
