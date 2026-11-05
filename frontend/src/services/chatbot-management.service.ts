import api from './api.service';

export interface KnowledgeCourse {
  course_name: string;
  course_display_name?: string;
  created_at?: string;
  user_type?: string;
}
export interface KnowledgeCategory { domain: string; usertype?: string }
export interface KnowledgeFile {
  _id: string;
  name: string;
  date_str?: string;
  in_vector_store?: string | boolean;
}
export interface KnowledgeActivity {
  _id: string;
  username: string;
  course_name: string;
  domain: string;
  file: string;
  action: string;
  date_str: string;
  time_str: string;
}
const base = '/chatbot-management/courses';
const coursePath = (course: string) => `${base}/${encodeURIComponent(course)}`;
const filesPath = (course: string, category: string) => `${coursePath(course)}/categories/${encodeURIComponent(category)}/files`;

export interface ChatbotDashboardData {
  courses: number;
  users: number;
  queries: number;
  usage: { label: string; count: number }[];
  by_course: { label: string; count: number }[];
}

export const chatbotManagementService = {
  async dashboard() {
    return (await api.get<ChatbotDashboardData>('/chatbot-management/dashboard')).data;
  },
  async overview() {
    return (await api.get<{ courses: number; users: number; conversations: number }>('/chatbot-management/overview')).data;
  },
  async activities() {
    return (await api.get<KnowledgeActivity[]>('/chatbot-management/activities')).data;
  },
  async courses() { return (await api.get<KnowledgeCourse[]>(base)).data; },
  async createCourse(body: { code: string; name: string; description: string }) {
    return (await api.post(base, body)).data;
  },
  async categories(course: string) {
    return (await api.get<KnowledgeCategory[]>(`${coursePath(course)}/categories`)).data;
  },
  async createCategory(course: string, name: string) {
    return (await api.post(`${coursePath(course)}/categories`, { name })).data;
  },
  async files(course: string, category: string) {
    return (await api.get<KnowledgeFile[]>(filesPath(course, category))).data;
  },
  async upload(course: string, category: string, files: File[]) {
    const body = new FormData();
    files.forEach((file) => body.append('files', file));
    return (await api.post(filesPath(course, category), body, { timeout: 600000 })).data;
  },
  async repairIndex(course: string) { return (await api.post(`${coursePath(course)}/index`)).data; },
  async chat(course: string, message: string, conversationId?: string) {
    return (await api.post<{ answer: string; conversation_id?: string }>(`${coursePath(course)}/chat`, {
      message, conversation_id: conversationId,
    }, { timeout: 200000 })).data;
  },
};
