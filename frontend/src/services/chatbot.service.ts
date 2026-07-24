import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';

export interface ChatbotRequest {
  question_id: number;
  user_message: string;
}

export interface ChatbotResponse {
  answer: string;
  timestamp: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

// ── New: AI Query Review interfaces ──────────────────────────────────────────

export interface QueryReviewResponse {
  problem_token: string;
  explanation: string;
  hint: string;
}

export interface LabQueryReviewResponse {
  db_state_issue: boolean;
  db_state_message: string;
  problem_token: string;
  explanation: string;
  hint: string;
}

// ─────────────────────────────────────────────────────────────────────────────

export const chatbotService = {
  // Existing: AI Tutor chat for SQL Questions (uses Dify)
  async sendMessage(request: ChatbotRequest): Promise<ChatbotResponse> {
    const response = await api.post<ChatbotResponse>(
      API_ENDPOINTS.CHATBOT.SEND,
      request
    );
    return response.data;
  },

  // NEW: Auto query review for SQL Questions (wrong but valid query)
  async reviewQuery(
    question_id: number,
    student_query: string
  ): Promise<QueryReviewResponse> {
    const response = await api.post<QueryReviewResponse>(
      API_ENDPOINTS.CHATBOT.QUERY_REVIEW,
      { question_id, student_query }
    );
    return response.data;
  },

  // NEW: Auto query review for SQL Lab task submissions
  async reviewLabQuery(
    lab_id: number,
    session_id: number,
    task_id: number,
    student_query: string
  ): Promise<LabQueryReviewResponse> {
    const response = await api.post<LabQueryReviewResponse>(
      API_ENDPOINTS.CHATBOT.LAB_QUERY_REVIEW,
      { lab_id, session_id, task_id, student_query }
    );
    return response.data;
  },

  // NEW: Conversational AI Tutor for SQL Labs
  async labChat(
    lab_id: number,
    session_id: number,
    user_message: string
  ): Promise<ChatbotResponse> {
    const response = await api.post<ChatbotResponse>(
      API_ENDPOINTS.CHATBOT.LAB_CHAT,
      { lab_id, session_id, user_message }
    );
    return response.data;
  },
};
