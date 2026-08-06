export interface CourseInfo {
  // The syllabus as Markdown. Rendered on the student page; edited by staff.
  content: string;
  updated_at: string | null;
  updated_by_email: string | null;
}

export interface CourseInfoUpdate {
  content: string;
}
