import { create } from 'zustand';
import type { FedexTelemetry } from '../api/fedex';

interface FedexState {
  telemetry: FedexTelemetry | null;
  begin: (snapshot: FedexTelemetry) => void;
  update: (snapshot: FedexTelemetry) => void;
  reset: () => void;
}
export const useFedexStore = create<FedexState>((set) => ({
  telemetry: null,
  begin: telemetry => set({telemetry}),
  update: telemetry => set(state => state.telemetry?.simulation_id === telemetry.simulation_id
    && telemetry.sequence >= state.telemetry.sequence ? {telemetry} : state),
  reset: () => set({telemetry:null}),
}));
