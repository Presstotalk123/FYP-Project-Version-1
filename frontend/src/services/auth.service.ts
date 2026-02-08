import api from './api.service';
import { API_ENDPOINTS } from '@/config/api.config';
import { LoginRequest, LoginResponse, RegisterRequest } from '@/types/api.types';
import { User } from '@/types/user.types';

export const authService = {
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await api.post<LoginResponse>(
      API_ENDPOINTS.AUTH.LOGIN,
      credentials
    );
    return response.data;
  },

  async register(data: RegisterRequest): Promise<User> {
    const response = await api.post<User>(API_ENDPOINTS.AUTH.REGISTER, data);
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
