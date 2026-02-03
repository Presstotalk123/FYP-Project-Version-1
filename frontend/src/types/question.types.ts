export enum Difficulty {
  EASY = 'easy',
  MEDIUM = 'medium',
  HARD = 'hard'
}

export interface Question {
  id: number;
  title: string;
  description: string;
  difficulty: Difficulty;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface QuestionDetail extends Question {
  schema_sql: string;
  sample_data_sql: string;
  db_file_path: string;
}

export interface QuestionCreate {
  title: string;
  description: string;
  difficulty: Difficulty;
  schema_sql: string;
  sample_data_sql: string;
  correct_answer_query: string;
}
