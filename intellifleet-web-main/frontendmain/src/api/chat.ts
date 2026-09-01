import apiClient from './client';
import type { ApiResponse, ChatResponse, ChatHistoryResponse } from '../types/api';

export const chatApi = {
  // Send message to AI agent
  sendMessage: async (message: string, sessionId?: string): Promise<ChatResponse> => {
    const response = await apiClient.post<ChatResponse>('/mcp-agent', {
      message,
      session_id: sessionId
    });
    return response.data;
  },

  getChatHistory: async (): Promise<ChatHistoryResponse> => {
    const response = await apiClient.get<ChatHistoryResponse>('/chat/history');
    return response.data;
  },

  // Check AI service health
  checkAIHealth: async (): Promise<ApiResponse<{ groq_available: boolean }>> => {
    const response = await apiClient.get<ApiResponse<{ groq_available: boolean }>>('/api/ai/health');
    return response.data;
  },
};

