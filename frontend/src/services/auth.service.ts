import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { GoogleAuthRequest, MicrosoftAuthRequest, LoginResponse } from '@/types/api.types';
import { User } from '@/types/user.types';

export const authService = {
  async googleLogin(token: string): Promise<LoginResponse> {
    const body: GoogleAuthRequest = { token };
    const response = await api.post<LoginResponse>(API_ENDPOINTS.AUTH.GOOGLE, body);
    return response.data;
  },

  async microsoftLogin(token: string): Promise<LoginResponse> {
    const body: MicrosoftAuthRequest = { token };
    const response = await api.post<LoginResponse>(API_ENDPOINTS.AUTH.MICROSOFT, body);
    return response.data;
  },

  async getCurrentUser(): Promise<User> {
    const response = await api.get<User>(API_ENDPOINTS.AUTH.ME);
    return response.data;
  },

  setToken(token: string): void {
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', token);
    }
  },

  getToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('access_token');
    }
    return null;
  },

  removeToken(): void {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
    }
  },

  logout(): void {
    this.removeToken();
  },
};

