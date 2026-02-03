import api from './api.service';
import { API_ENDPOINTS } from '../config/api.config';
import { LoginRequest, LoginResponse, RegisterRequest } from '../types/api.types';
import { User } from '../types/user.types';

export const authService = {
  /**
   * Login with email and password
   */
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await api.post<LoginResponse>(
      API_ENDPOINTS.AUTH.LOGIN,
      credentials
    );
    return response.data;
  },

  /**
   * Register a new user
   */
  async register(data: RegisterRequest): Promise<User> {
    const response = await api.post<User>(API_ENDPOINTS.AUTH.REGISTER, data);
    return response.data;
  },

  /**
   * Get current user information
   */
  async getCurrentUser(): Promise<User> {
    const response = await api.get<User>(API_ENDPOINTS.AUTH.ME);
    return response.data;
  },

  /**
   * Store JWT token in localStorage
   */
  setToken(token: string): void {
    localStorage.setItem('access_token', token);
  },

  /**
   * Get JWT token from localStorage
   */
  getToken(): string | null {
    return localStorage.getItem('access_token');
  },

  /**
   * Remove JWT token from localStorage
   */
  removeToken(): void {
    localStorage.removeItem('access_token');
  },

  /**
   * Logout - clear token
   */
  logout(): void {
    this.removeToken();
  },
};
