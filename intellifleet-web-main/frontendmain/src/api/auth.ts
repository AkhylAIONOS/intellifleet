import apiClient from './client';
import type { ApiResponse, LoginRequest, SignupRequest, AuthResponse, User } from '../types/api';

export const authApi = {
  demoAccess: async (identity: {name:string;email:string}): Promise<ApiResponse<AuthResponse & { user: User }>> => {
    const response = await apiClient.post<ApiResponse<AuthResponse & { user: User }>>('/auth/demo-access', identity);
    return response.data;
  },
  users: async (): Promise<{users:Array<{name:string;email:string;first_login_at:string;last_login_at:string;login_count:number}>}> => (await apiClient.get('/auth/users')).data,
  // Sign in
  signin: async (credentials: LoginRequest): Promise<ApiResponse<AuthResponse>> => {
    const response = await apiClient.post<ApiResponse<AuthResponse>>('/auth/signin', credentials);
    return response.data;
  },

  // Sign up
  signup: async (userData: SignupRequest): Promise<ApiResponse> => {
    const response = await apiClient.post<ApiResponse>('/auth/signup', userData);
    return response.data;
  },

  // Get current user
  getCurrentUser: async (): Promise<ApiResponse<{ user: User }>> => {
    const response = await apiClient.get<ApiResponse<{ user: User }>>('/me');
    return response.data;
  },
};
