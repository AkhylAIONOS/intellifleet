import { decodePolyline } from './decodePolyline';

export interface Point { lat: number; lng: number }
export interface PlanLeg {
  route_id?: number; from_location: string; to_location: string; route_type: string;
  source_coords?: Point; destination_coords?: Point; path?: Point[] | string;
  polyline?: Point[] | string; overview_polyline?: string;
  distance?: number; duration?: number; is_active?: boolean; disrupted?: boolean;
}
export interface Assignment {
  id: number; route_id?: number; leg_index?: number; label?: string; type?: string; capacity?: number;
  assigned_load_kg?: number; utilization_percentage?: number;
}
export interface VisualPlan {
  plan_id?: string; mode: string; route_legs: PlanLeg[]; vehicles?: Assignment[];
  leg_assignments?: {route_legs: PlanLeg[]; vehicles: Assignment[]}[];
  operational_cost?: number; duration_hours?: number; risk_score?: number;
  reliability?: number; vehicle_utilization?: number; distance_km?: number;
}
export interface PlanComparison {
  before: VisualPlan; after: VisualPlan; beforeLabel: string; afterLabel: string;
  differences?: { cost_difference?: number; eta_difference_hours?: number; risk_difference?: number };
}
export interface WarehouseFocus {
  warehouse_id?: number; warehouse?: string; latitude?: number; longitude?: number;
  current_inventory?: number; available_inventory?: number; available_storage?: number;
  utilization_percentage?: number; storage_capacity?: number;
}
// Normalize optional transport metadata once at the selection boundary. Preserve
// every supplied assignment object and its exact numeric values.
export function normalizedAssignments(value: unknown): Assignment[] {
  if (value == null) return [];
  const rows = Array.isArray(value) ? value : [value];
  if (rows.every(row => row && typeof row === 'object' && !Array.isArray(row))) return rows as Assignment[];
  return rows.filter(row => row && typeof row === 'object' && !Array.isArray(row)) as Assignment[];
}
export function normalizeVisualPlan(plan: VisualPlan): VisualPlan {
  const vehicles = normalizedAssignments(plan.vehicles);
  const legs = Array.isArray(plan.route_legs) ? plan.route_legs : [];
  const route_legs = legs.every(leg => leg && typeof leg === 'object') ? legs : legs.filter(leg => leg && typeof leg === 'object');
  return vehicles === plan.vehicles && route_legs === plan.route_legs ? plan : {...plan, vehicles, route_legs};
}
export const validPoint = (p: unknown): p is Point => {
  const point = p as Point | undefined;
  return !!point && Number.isFinite(point.lat) && Number.isFinite(point.lng) && Math.abs(point.lat) <= 90 && Math.abs(point.lng) <= 180;
};
export function legPoints(leg: PlanLeg | null | undefined): Point[] {
  if (!leg) return [];
  const raw = leg.path ?? leg.polyline ?? leg.overview_polyline;
  let points: Point[] = [];
  try { points = typeof raw === 'string' ? decodePolyline(raw) : Array.isArray(raw) ? raw : []; } catch { /* Fall back to supplied endpoints. */ }
  if (points.length >= 2 && points.every(validPoint)) return points;
  return validPoint(leg.source_coords) && validPoint(leg.destination_coords) ? [leg.source_coords, leg.destination_coords] : [];
}
// Length weighting is exclusively for demo playback, never operational ETA/distance.
export function journeySegments(plan: VisualPlan) {
  return normalizeVisualPlan(plan).route_legs.flatMap((leg, legIndex) => {
    const points = legPoints(leg);
    return points.slice(1).map((to, i) => {
      const from = points[i];
      const dy = (to.lat - from.lat) * Math.PI / 180;
      const dx = (to.lng - from.lng) * Math.PI / 180;
      const a = Math.sin(dy / 2) ** 2 + Math.cos(from.lat * Math.PI / 180) * Math.cos(to.lat * Math.PI / 180) * Math.sin(dx / 2) ** 2;
      return { from, to, mode: leg.route_type, legIndex, length: 2 * Math.asin(Math.sqrt(Math.min(1, a))) };
    });
  });
}
export function journeyPosition(segments: ReturnType<typeof journeySegments>, progress: number) {
  if (!segments.length) return null;
  const total = segments.reduce((sum, s) => sum + s.length, 0);
  let remaining = Math.min(1, Math.max(0, progress)) * total;
  for (const [index, segment] of segments.entries()) {
    if (remaining < segment.length || index === segments.length - 1) {
      const t = segment.length ? Math.min(1, remaining / segment.length) : 1;
      return { lat: segment.from.lat + (segment.to.lat - segment.from.lat) * t,
        lng: segment.from.lng + (segment.to.lng - segment.from.lng) * t, mode: segment.mode, legIndex: segment.legIndex };
    }
    remaining -= segment.length;
  }
  return null;
}
export function continuousJourney(plan: VisualPlan) {
  const legs = normalizeVisualPlan(plan).route_legs;
  return legs.length > 0 && legs.every((leg, i, legs) => {
    const points = legPoints(leg);
    const previous = i ? legPoints(legs[i - 1]).at(-1) : undefined;
    return points.length >= 2 && (!i || (previous?.lat === points[0].lat && previous?.lng === points[0].lng));
  });
}
export const planRouteName = (plan: VisualPlan) => {
  const legs = normalizeVisualPlan(plan).route_legs;
  return legs.length ? [legs[0].from_location, ...legs.map(leg => leg.to_location)].filter(Boolean).join(' → ') : '';
};
