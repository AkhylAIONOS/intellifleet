import apiClient from './client';
import type { InventoryResponse } from '../types/api';

export const warehouseApi = {
    getInventory: async (): Promise<InventoryResponse> => {
        const response = await apiClient.get<InventoryResponse>('/inventory');
        return response.data;
    }
};