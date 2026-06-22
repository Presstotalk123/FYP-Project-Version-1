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

export const chatbotService = {
  async sendMessage(request: ChatbotRequest): Promise<ChatbotResponse> {
    const response = await api.post<ChatbotResponse>(
      API_ENDPOINTS.CHATBOT.SEND,
      request
    );
    return response.data;
  },
};
