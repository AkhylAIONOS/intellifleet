import apiClient from './client';
import type { Warehouse, UploadResponse } from '../types/api';

export const warehousesApi = {
  // Get all warehouses
  // getWarehouses: async (): Promise<ApiResponse<{ warehouses: Warehouse[]; total_warehouses: number }>> => {
  //   const response = await apiClient.get<ApiResponse<{ warehouses: Warehouse[]; total_warehouses: number }>>('/warehouses/');
  //   return response.data;
  // },

  // getWarehouses: async (): Promise<{ warehouses: Warehouse[]; total_warehouses: number }> => {
  //   const response = await apiClient.get<{ warehouses: Warehouse[]; total_warehouses: number }>('/warehouses');
  //   return response.data;
  // },

  getWarehouses: async (): Promise<{ warehouses: Warehouse[]; total_warehouses: number }> => {
    const response = await apiClient.get<{
      success: boolean;
      status_code: number;
      message: string;
      data: { warehouses: Warehouse[]; total_warehouses: number };
    }>('/warehouses');
    return response.data.data;  // Access the nested 'data' object
  },

  // Upload CSV
  uploadCSV: async (file: File): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<UploadResponse>('/upload_csv', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

