export enum Difficulty {
  EASY = 'easy',
  MEDIUM = 'medium',
  HARD = 'hard',
}

export interface Question {
  id: number;
  title: string;
  description: string;
  difficulty: Difficulty;
  created_by: number;
  created_at: string;
  updated_at: string;
  is_published: boolean;
  // LeetCode problem number for imported questions (drives DATABASE_README_EN.md
  // ordering); null/undefined for hand-authored questions.
  leetcode_id?: number | null;
}

export interface QuestionDetail extends Question {
  schema_sql: string;
  sample_data_sql: string;
  db_file_path: string;
  correct_answer_query?: string | null;
  advanced_sql_testing: boolean;
  test_script?: string | null;
  check_query?: string | null;
  hide_correctness: boolean;
  order_sensitive: boolean;
}

export interface QuestionCount {
  // Size of the student-visible published question bank (backend-cached).
  total: number;
  // How many of those the current user has attempted at least once.
  attempted: number;
}

export interface QuestionCreate {
  title: string;
  description: string;
  difficulty: Difficulty;
  schema_sql: string;
  sample_data_sql: string;
  correct_answer_query: string;
  advanced_sql_testing?: boolean;
  test_script?: string | null;
  check_query?: string | null;
  hide_correctness?: boolean;
  order_sensitive?: boolean;
}
