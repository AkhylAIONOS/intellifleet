import apiClient from './client';
import { API_BASE_URL } from '../config/env';

export interface Candidate {
  schedule_id: string; origin: string; gateway: string; mode: string; run: string; service: string;
  cutoff: string | null; etd: string | null; eta: string | null; retrieval: string | null;
  eligible: boolean; reason: string; warnings: string[];
}
export interface Eligibility {
  candidates: Candidate[]; selected: Candidate | null; selection_reason: string; schedule_notice: string;
}
export interface FedexInput {
  origin_station: string; gateway: string; simulation_date: string; shipment_ready_datetime: string;
  speed?: number; schedule_id?: string;
}
export interface FedexTelemetry {
  simulation_id: string; shipment_id: string; origin_station: string; gateway: string; mode: string;
  run: string; service: string; simulation_timestamp: string; latitude: number; longitude: number;
  progress: number; status: string; paused: boolean; stopped: boolean; simulation_speed: number;
  scheduled_etd: string; scheduled_eta: string; current_eta: string; cutoff: string; retrieval: string | null;
  synthetic_data: true; location_source: 'DEMO_SIMULATION'; route: [number, number][]; sequence: number;
  alerts: Array<{ title: string; severity: string; impact: string; recommended_action: string; reason: string;
    eligible_alternatives: Candidate[]; alternatives_condition: string }>;
}
export interface ScheduleSummary {
  lanes: Array<{ origin_station: string; gateway: string; simulation_supported: boolean }>;
  schedule_notice: string;
}

export const fedexApi = {
  summary: async (): Promise<ScheduleSummary> => (await apiClient.get('/fedex/schedules')).data,
  eligible: async (input: FedexInput): Promise<Eligibility> => (await apiClient.get('/fedex/eligible-services', { params: input })).data,
  create: async (input: FedexInput): Promise<FedexTelemetry> => (await apiClient.post('/fedex/simulations', input)).data,
  event: async (id: string, minutes: number): Promise<FedexTelemetry> =>
    (await apiClient.post(`/fedex/simulations/${id}/events`, {event_type:'DELAY', expected_delay_minutes: minutes})).data,
  control: async (id: string, action: string, speed?: number) =>
    (await apiClient.post(`/fedex/simulations/${id}/control`, {action, speed})).data,
};

export function parseTelemetryFrame(frame: string): FedexTelemetry | null {
  if (!frame.split('\n').some(line => line.trim() === 'event: telemetry')) return null;
  const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n');
  const value = JSON.parse(data);
  if (typeof value.simulation_id !== 'string' || !Number.isFinite(value.latitude) || !Number.isFinite(value.longitude)
      || !Number.isFinite(value.progress) || value.progress < 0 || value.progress > 1 || value.synthetic_data !== true) {
    throw new Error('Invalid telemetry snapshot');
  }
  return value;
}

// fetch preserves the existing bearer-token convention; no credentials in URLs.
export async function streamTelemetry(id: string, signal: AbortSignal, onData: (s: FedexTelemetry) => void,
                                      onConnection: (state: string) => void) {
  while (!signal.aborted) {
    let terminal = false;
    try {
      const token = localStorage.getItem('authToken');
      const response = await fetch(`${API_BASE_URL.replace(/\/$/, '')}/fedex/simulations/${id}/stream`, {
        headers: {Authorization: `Bearer ${token || ''}`, Accept: 'text/event-stream'}, signal,
      });
      if ([401, 403, 404].includes(response.status)) {
        onConnection(response.status === 404 ? 'Simulation expired; reset to start again' : 'Authentication expired; sign in again');
        return;
      }
      if (!response.ok || !response.body) throw new Error('Telemetry unavailable');
      onConnection('Live');
      const reader = response.body.getReader();
      const decoder = new TextDecoder(); let buffer = '';
      try {
        while (!signal.aborted) {
          const {done, value} = await reader.read(); if (done) break;
          buffer += decoder.decode(value, {stream: true}).replace(/\r/g, '');
          let boundary;
          while ((boundary = buffer.indexOf('\n\n')) >= 0) {
            const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
            if (frame.includes('event: expired')) {onConnection('Simulation expired; reset to start again'); return;}
            const snapshot = parseTelemetryFrame(frame);
            if (snapshot) {
              onData(snapshot);
              terminal = snapshot.stopped || snapshot.status === 'ARRIVED_AT_GTW';
            }
          }
          if (terminal) {onConnection('Complete / stopped'); return;}
        }
      } finally {await reader.cancel().catch(() => {}); reader.releaseLock();}
    } catch {if (signal.aborted) return;}
    if (signal.aborted || terminal) return;
    onConnection('Reconnecting…');
    await new Promise<void>(resolve => {
      const finish = () => {clearTimeout(timer); signal.removeEventListener('abort', finish); resolve();};
      const timer = setTimeout(finish, 1500); signal.addEventListener('abort', finish, {once:true});
    });
  }
}
