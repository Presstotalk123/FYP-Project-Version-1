export interface ApiResponse<T> {
  data: T;
  message?: string;
}

export interface ApiError {
  detail: string;
}

export interface GoogleAuthRequest {
  token: string;
}

export interface MicrosoftAuthRequest {
  token: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}
