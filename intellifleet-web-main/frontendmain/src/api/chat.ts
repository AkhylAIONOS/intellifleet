import {useOperationsStore} from '../store/operationsStore';
import {useFedexStore} from '../store/fedexStore';
import apiClient from './client';
import {useControlTowerStore} from '../store/controlTowerStore';
import type { ApiResponse, ChatResponse, ChatHistoryResponse } from '../types/api';

export const chatApi = {
  // Send message to AI agent
  sendMessage: async (message: string, sessionId?: string): Promise<ChatResponse> => {
    const response = await apiClient.post<ChatResponse>('/mcp-agent', {
      message,
      workspace: useControlTowerStore.getState().workspace,
      selected_operational_run_id: useControlTowerStore.getState().workspace==='LIVE OPERATIONS'?useControlTowerStore.getState().selected?.run_id:undefined,
      selected_operational_run_ids: useControlTowerStore.getState().workspace==='LIVE OPERATIONS'?useControlTowerStore.getState().selectedRuns.map(run=>run.run_id):undefined,
      operational_service_date: useControlTowerStore.getState().serviceDate || useControlTowerStore.getState().selected?.service_date,
      selected_simulation_id: useControlTowerStore.getState().workspace==='LIVE OPERATIONS'?undefined:useOperationsStore.getState().selected || useFedexStore.getState().telemetry?.simulation_id,
      session_id: sessionId
    });
    return response.data;
  },

  getChatHistory: async (): Promise<ChatHistoryResponse> => {
    const response = await apiClient.get<ChatHistoryResponse>('/chat/history');
    return response.data;
  },

  clearChat: async (): Promise<void> => {
    await apiClient.delete('/chat/history');
  },

  // Check AI service health
  checkAIHealth: async (): Promise<ApiResponse<{ groq_available: boolean }>> => {
    const response = await apiClient.get<ApiResponse<{ groq_available: boolean }>>('/api/ai/health');
    return response.data;
  },
};
