import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { CourseInfo } from '@/types/course.types';

export const courseService = {
  // Student + staff read the same syllabus content (backend-cached).
  async get(): Promise<CourseInfo> {
    const response = await api.get<CourseInfo>(API_ENDPOINTS.COURSE_INFO.BASE);
    return response.data;
  },

  // Staff-only overwrite of the syllabus Markdown.
  async update(content: string): Promise<CourseInfo> {
    const response = await api.put<CourseInfo>(API_ENDPOINTS.COURSE_INFO.BASE, { content });
    return response.data;
  },
};
