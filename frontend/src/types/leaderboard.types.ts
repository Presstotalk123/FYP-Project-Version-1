export type LabTaskStatus = 'solved' | 'attempted' | 'not_attempted';

/** One task column of the per-lab leaderboard, in the lab's task order. */
export interface LabLeaderboardTask {
  task_id: number;
  title: string;
  order_index: number;
}

/**
 * One student's standing in a lab. For student viewers, `student_id` and `email`
 * are always null and other students' `display_name` is masked (e.g. "Ad****** Ch**").
 */
export interface LabLeaderboardRow {
  rank: number;
  student_id: number | null;
  display_name: string;
  email: string | null;
  class_group: string | null;
  tasks_correct: number;
  total_tasks: number;
  /** Per task, in the same order as `LabLeaderboardResponse.tasks`. */
  task_status: LabTaskStatus[];
  submissions: number;
  /** When the student reached their current score (ISO datetime), or null if nothing solved. */
  finished_at: string | null;
  completed: boolean;
  is_me: boolean;
}

export interface LabLeaderboardResponse {
  lab_id: number;
  title: string;
  lab_type: string;
  tasks: LabLeaderboardTask[];
  rows: LabLeaderboardRow[];
  class_groups: string[];
  /** The student viewer's own rank, if they are listed. Always null for staff. */
  my_rank: number | null;
  /** True when the lab hides correctness from students; `rows` is then empty. */
  correctness_hidden: boolean;
}

/** One student's practice completions across SQL questions, ER questions and labs. */
export interface OverallLeaderboardRow {
  rank: number;
  student_id: number | null;
  display_name: string;
  email: string | null;
  class_group: string | null;
  sql_completed: number;
  erd_completed: number;
  labs_completed: number;
  total: number;
  is_me: boolean;
}

export interface OverallLeaderboardResponse {
  rows: OverallLeaderboardRow[];
  class_groups: string[];
  my_rank: number | null;
}
