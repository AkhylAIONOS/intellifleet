import apiClient from './client';
import type { Vehicle, VehicleCompletePayload, VehicleCompleteResponse } from '../types/api';


export const vehiclesApi = {
  // Get all vehicles
  getVehicles: async (): Promise<{ vehicles: Vehicle[]; total_vehicles: number }> => {
    const response = await apiClient.get<{
      success: boolean;
      status_code: number;
      message: string;
      data: {vehicles: Vehicle[]; total_vehicles: number};
    }>('/vehicles');
    return response.data.data;
  },

  // Complete vehicle route
  completeRoute: async (payload: VehicleCompletePayload): Promise<VehicleCompleteResponse> => {
    const response = await apiClient.post<VehicleCompleteResponse>('/vehicles_complete', payload);
    return response.data;
  },

  assignMultimodal: async (routeId: number): Promise<any> => {
    const response = await apiClient.post('/multimodal_assign_vehicle', { route_id: routeId });
    return response.data;
  },

  fetchNextSegment: async (sessionId: string): Promise<any> => {
    const response = await apiClient.get(`/assign-partial-next?session_id=${sessionId}`);
    return response.data;
  },

};

