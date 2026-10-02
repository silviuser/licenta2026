import { apiClient } from './client';
import type { LoginRequest, LoginResponse, RegisterRequest, UserResponse } from './types';

export async function register(body: RegisterRequest): Promise<UserResponse> {
  const { data } = await apiClient.post<UserResponse>('/api/auth/register', body);
  return data;
}

export async function login(body: LoginRequest): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/api/auth/login', body);
  return data;
}

export async function getMe(): Promise<UserResponse> {
  const { data } = await apiClient.get<UserResponse>('/api/auth/me');
  return data;
}
