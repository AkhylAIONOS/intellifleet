import apiClient from './client';

export interface PlanningInput {
  source: string;
  destination: string;
  shipment: { weight_kg: number; quantity: number; sku?: string };
  objective: 'cheapest' | 'fastest' | 'lowest-risk' | 'balanced';
  deadline?: string;
  allowed_modes: Array<'road' | 'air' | 'multimodal'>;
  target_margin: number;
  max_risk?: number;
}

export const planningApi = {
  createPlan: async (input: PlanningInput) => (await apiClient.post('/planning/plans', input)).data,
  createScenario: async (planning_request: PlanningInput, changes: Record<string, unknown>) =>
    (await apiClient.post('/planning/scenarios', { planning_request, changes })).data,
  scenarioAction: async (id: string, action: 'apply' | 'discard') =>
    (await apiClient.post(`/planning/scenarios/${id}/${action}`)).data,
  operation: async (path: string, body?: unknown) => (await (body ? apiClient.post(`/planning/${path}`, body) : apiClient.get(`/planning/${path}`))).data,
};
