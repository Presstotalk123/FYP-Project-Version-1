import api from './api.service';
import { API_ENDPOINTS, API_BASE_URL } from '@/config/api.config';

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

// ── Persisted tutor transcript (restore on mount) ────────────────────────────

export interface StoredTutorMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string | null;
  created_at: string | null;
}

export interface TutorConversationResponse {
  exists: boolean;
  conversation_id: number | null;
  context_type?: 'question' | 'lab';
  messages: StoredTutorMessage[];
}

// ─────────────────────────────────────────────────────────────────────────────

export const chatbotService = {
  // AI Tutor chat for SQL Questions (Streaming, provider-configurable)
  async streamQuestionChat(
    question_id: number,
    user_message: string
  ): Promise<Response> {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    return fetch(`${API_BASE_URL}${API_ENDPOINTS.CHATBOT.SEND}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question_id, user_message }),
    });
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

  // NEW: Conversational AI Tutor for SQL Labs (Streaming)
  async streamLabChat(
    lab_id: number,
    session_id: number,
    user_message: string
  ): Promise<Response> {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    return fetch(`${API_BASE_URL}${API_ENDPOINTS.CHATBOT.LAB_CHAT}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ lab_id, session_id, user_message }),
    });
  },

  // NEW: Restore the current user's saved SQL-question tutor transcript
  async getQuestionConversation(
    question_id: number
  ): Promise<TutorConversationResponse> {
    const response = await api.get<TutorConversationResponse>(
      API_ENDPOINTS.CHATBOT.CONVERSATION,
      { params: { question_id } }
    );
    return response.data;
  },

  // NEW: Restore the current user's saved SQL-lab tutor transcript for a session
  async getLabConversation(
    lab_id: number,
    session_id: number
  ): Promise<TutorConversationResponse> {
    const response = await api.get<TutorConversationResponse>(
      API_ENDPOINTS.CHATBOT.LAB_CONVERSATION,
      { params: { lab_id, session_id } }
    );
    return response.data;
  },

  // NEW: Conversational course assistant for the course info page (Streaming)
  async streamCourseChat(
    course_context: string,
    user_message: string
  ): Promise<Response> {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    return fetch(`${API_BASE_URL}${API_ENDPOINTS.CHATBOT.COURSE_CHAT}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ course_context, user_message }),
    });
  },
};
