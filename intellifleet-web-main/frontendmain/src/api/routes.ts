// import apiClient from './client';
// import type { RouteSessionResponse } from '../types/api';

// export const routesApi = {
//     // Get route session for cross-device sync
//     getRouteSession: async (): Promise<RouteSessionResponse> => {
//         const response = await apiClient.get<RouteSessionResponse>('/route_session');
//         return response.data;
//     },
// };

import apiClient from './client';
import type { RouteSessionResponse } from '../types/api';

export interface RouteUploadEntry {
    source: string;
    destination: string;
    intermediate: string[];
    type: 'road' | 'air';
    // objective: 'cost' | 'duration' | 'distance';
}

export interface RouteUploadJsonResponse {
    success: boolean;
    upload_type: string;
    message: string;
    data: {
        road_routes: any[];
        multimodal_routes: any[];
        air_intermediate_route: any[];
    };
    errors: any[];
}

export const routesApi = {
    // Get route session for cross-device sync
    getRouteSession: async (): Promise<RouteSessionResponse> => {
        const response = await apiClient.get<RouteSessionResponse>('/route_session');
        return response.data;
    },

    // Upload routes via JSON table
    uploadRoutesJson: async (routes: RouteUploadEntry[]): Promise<RouteUploadJsonResponse> => {
        const response = await apiClient.post<RouteUploadJsonResponse>('/upload-routes-json', {
            routes,
        });
        return response.data;
    },
    updateRoute: async (routeId: number, updates: { is_active: boolean; distance: number; duration: number; cost: number }) =>
        (await apiClient.patch(`/routes/${routeId}`, updates)).data,
};
