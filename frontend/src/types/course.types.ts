export interface CourseInfo {
  // The syllabus as Markdown. Rendered on the student page; edited by staff.
  content: string;
}

export interface CourseInfoUpdate {
  content: string;
}
