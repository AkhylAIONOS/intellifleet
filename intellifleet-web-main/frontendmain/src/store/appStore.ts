import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { normalizeVisualPlan, continuousJourney, legPoints, type VisualPlan, type PlanComparison, type WarehouseFocus } from '../utils/planVisuals';
import type { Warehouse, Vehicle, ActiveRoute } from '../types/api';
import type { WarehouseInventory } from '../types/api';

// Module-level ref for segment completion callback — kept OUTSIDE Zustand
// state so React's performance profiling never tries to clone it.
let _onSegmentComplete: (() => void) | null = null;

interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    timestamp: number;
}

interface ActivePlane {
    id: string;
    routeId: number;
    sourceAirport: { lat: number; lng: number; name: string };
    destAirport: { lat: number; lng: number; name: string };
    currentPosition: { lat: number; lng: number };
    status: 'flying' | 'landed' | 'removed';
}

interface AppState {
    // Data
    warehouses: Warehouse[];
    warehouseInventory: WarehouseInventory[];
    vehicles: Vehicle[];
    activeRoutes: Record<number, ActiveRoute>;
    chatHistory: ChatMessage[];

    operationResult: Record<string, unknown> | null;
    selectedPlan: VisualPlan | null;
    planComparison: PlanComparison | null;
    planNotice: string | null;
    warehouseFocus: WarehouseFocus | null;
    planningVehicleBackups: Record<number, Vehicle>;
    clearPlanningVisuals: () => void;

    // UI State
    isLoading: boolean;
    isDashboardOpen: boolean;
    selectedVehicleId: number | null;
    mapViewMode: 'street' | 'satellite';
    activePlanes: ActivePlane[];
    hasCsvUploaded: boolean;
    activeDashboard: 'activeRoutes' | 'warehouse' | 'vehicleInfo' | 'vehicleDashboard' | null;
    lastAssignedRouteId: number | null;
    lastCreatedRouteId: number | null;
    highlightedRouteIds: number[];
    segmentSession: { sessionId: string; partial: boolean; segmentIndex: number; totalSegments: number; } | null;
    pendingVehiclesCount: number;

    // Actions
    setWarehouses: (warehouses: Warehouse[]) => void;
    setVehicles: (vehicles: Vehicle[]) => void;
    updateWarehouse: (warehouseId: number, updates: Partial<Warehouse>) => void;
    setWarehouseInventory: (inventory: WarehouseInventory[]) => void;
    updateVehicle: (vehicle: Vehicle) => void;
    //markVehicleCompleted: (vehicleId: number, destination: string) => void;
    markVehicleCompleted: (vehicleId: number, destination: string, finalPosition: { lat: number; lng: number }) => void;
    markRouteAsInactive: (routeId: number) => void;
    updateActiveRouteStatus: (routeId: number, isActive: boolean) => void;

    addActiveRoute: (route: ActiveRoute) => void;
    updateActiveRoute: (routeId: number, route: ActiveRoute) => void;
    removeActiveRoute: (routeId: number) => void;
    clearActiveRoutes: () => void;
    setActiveRoutes: (routes: Record<number, ActiveRoute>) => void;
    addPlane: (plane: ActivePlane) => void;
    updatePlane: (id: string, updates: Partial<ActivePlane>) => void;
    removePlane: (id: string) => void;

    addChatMessage: (role: 'user' | 'assistant', content: string) => void;
    setChatHistory: (messages: { role: 'user' | 'assistant'; content: string }[]) => void;
    clearChatHistory: () => void;

    setLoading: (loading: boolean) => void;
    toggleDashboard: () => void;
    setSelectedVehicle: (id: number | null) => void;
    setMapViewMode: (mode: 'street' | 'satellite') => void;
    setHasCsvUploaded: (value: boolean) => void;
    setActiveDashboard: (dashboard: 'activeRoutes' | 'warehouse' | 'vehicleInfo' | 'vehicleDashboard' | null) => void;
    setLastAssignedRouteId: (routeId: number | null) => void;
    setLastCreatedRouteId: (routeId: number | null) => void;
    setHighlightedRouteIds: (routeIds: number[]) => void;
    setSegmentSession: (session: AppState['segmentSession']) => void;
    setOnSegmentComplete: (callback: (() => void) | null) => void;
    setPendingVehiclesCount: (count: number) => void;
    decrementPendingVehicles: () => void;
    applyPlanningMapPlan: (data: any) => number | null;

    // Reset
    resetStore: () => void;
}

export const useAppStore = create<AppState>()(
    persist(
        (set, get) => ({
            operationResult: null, selectedPlan: null, planComparison: null, planNotice: null, warehouseFocus: null,
            planningVehicleBackups: {},
            clearPlanningVisuals: () => set(state => ({
                operationResult: null, selectedPlan: null, planComparison: null, planNotice: null, warehouseFocus: null,
                activeRoutes: Object.fromEntries(Object.entries(state.activeRoutes).filter(([, route]) => !route.routeData?.planning)),
                vehicles: state.vehicles.map(v => state.planningVehicleBackups[v.id] || v),
                planningVehicleBackups: {},
                activePlanes: state.activePlanes.filter(p => !p.id.startsWith('planning-')),
                lastCreatedRouteId: null, lastAssignedRouteId: null,
            })),
            // Initial Data
            warehouses: [],
            vehicles: [],
            activeRoutes: {},
            chatHistory: [],
            warehouseInventory: [],



            // Initial UI State
            isLoading: false,
            isDashboardOpen: true,
            selectedVehicleId: null,
            mapViewMode: 'street',
            hasCsvUploaded: false,
            activePlanes: [],
            activeDashboard: null,
            lastAssignedRouteId: null,
            lastCreatedRouteId: null,
            highlightedRouteIds: [],
            segmentSession: null,
            pendingVehiclesCount: 0,

            // Actions

            setWarehouses: (warehouses) => set({ warehouses }),
            updateWarehouse: (warehouseId, updates) =>
                set((state) => ({
                    warehouses: state.warehouses.map((w) =>
                        w.id === warehouseId || w.warehouse_id === warehouseId
                            ? { ...w, ...updates }
                            : w
                    ),
                })),
            setVehicles: (vehicles) => set({ vehicles }),
            setWarehouseInventory: (inventory) => set({ warehouseInventory: inventory }),
            applyPlanningMapPlan: (data) => {
                if (!data || typeof data !== "object" || Array.isArray(data)) return null;
                set({operationResult: data});
                const state = get();
                if (data.planning_operation === 'warehouse_capacity') {
                    const rows = data.warehouses || [];
                    // A scoped structured result is authoritative. Never guess among multiple warehouses.
                    set({ warehouseFocus: rows.length === 1 ? {...rows[0]} : null,
                        warehouses:state.warehouses.map(w => { const row=rows.find((r:WarehouseFocus)=>String(r.warehouse_id)===String(w.warehouse_id ?? w.id));
                            return row ? {...w, inventory:row.current_inventory, available_inventory:row.available_inventory,
                                available_storage:row.available_storage, utilization_percentage:row.utilization_percentage,storage_capacity:row.storage_capacity} : w; }) });
                    return null;
                }
                const recovery = Object.prototype.hasOwnProperty.call(data, 'recovery_plan');
                const scenario = data.scenario && data.baseline;
                const before = data.baseline?.recommended_plan;
                const after = data.scenario?.recommended_plan;
                if (scenario && !recovery && data.status !== 'applied') {
                    set({ planComparison: before && after ? {before, after, beforeLabel:'Baseline', afterLabel:'Scenario', differences:data.comparison} : null,
                        planNotice: after ? 'Draft scenario — current plan unchanged.' : 'No feasible scenario plan — current plan retained.' });
                    return null;
                }
                if (data.status === 'discarded') {
                    set({planComparison:null, planNotice:'Scenario discarded — current plan unchanged.'});
                    return null;
                }
                const candidates = recovery ? [data.recovery_plan?.recommended_plan, data.recovery_plan] :
                    [data.approved_plan, data.recommended_plan, ...(data.allocation || []).map((item: any) => item.plan)];
                const candidate = candidates.find((item: any) => item && typeof item === 'object' && (item.plan_id || item.route_legs || item.vehicles));
                const plan: VisualPlan | undefined = candidate ? normalizeVisualPlan(candidate) : undefined;
                if (!plan) {
                    if (recovery || Object.prototype.hasOwnProperty.call(data, 'recommended_plan'))
                        set({planNotice: state.selectedPlan ? 'No feasible revised plan — current plan retained.' : 'No feasible plan available.', planComparison:null});
                    return null;
                }
                const modeBefore = data.options?.ground;
                const modeAfter = data.options?.express;
                const comparison: PlanComparison | null = modeBefore && modeAfter
                    ? {before:modeBefore, after:modeAfter, beforeLabel:'Ground', afterLabel:'Express', differences:data.express_vs_ground ? {
                        cost_difference:data.express_vs_ground.additional_cost, eta_difference_hours:-data.express_vs_ground.time_saved_hours,
                        risk_difference:data.express_vs_ground.risk_difference} : undefined}
                    : (before || state.selectedPlan) ? {before:before || state.selectedPlan, after:plan,
                        beforeLabel:before ? 'Baseline' : 'Current', afterLabel:'Revised', differences:data.comparison} : null;
                const path = plan.route_legs.flatMap(legPoints);
                // The snapshot remains useful even when network geometry is missing.
                const request = data.planning_request || data.scenario?.planning_request || {};
                const source = request.source || plan.route_legs[0]?.from_location || 'Origin unavailable';
                const destination = request.destination || plan.route_legs.at(-1)?.to_location || 'Destination unavailable';
                const identity = String(plan.plan_id || `${source}-${destination}`);
                let routeId = -1 - Math.abs(identity.split('').reduce((value: number, character: string) => ((value << 5) - value) + character.charCodeAt(0), 0));
                while (state.activeRoutes[routeId] && !state.activeRoutes[routeId].routeData?.planning) routeId--;
                const route: ActiveRoute = { id: routeId, source, destination,
                    intermediates: plan.route_legs.slice(0,-1).map((leg: any) => leg.to_location),
                    waypoints: [source,...plan.route_legs.slice(0,-1).map(leg => leg.to_location),destination], created: new Date(), isActive: true,
                    routeData: { optimal_routes: [{path,distance:plan.distance_km,duration:plan.duration_hours,isOptimal:true}],
                        route_cost:plan.operational_cost, planning:true, legs:plan.route_legs, plan_id:plan.plan_id,
                        assigned_vehicles:plan.vehicles || [] } };
                set((state) => {
                    const retainedRoutes = Object.fromEntries(Object.entries(state.activeRoutes)
                        .filter(([,existing]) => !existing.routeData?.planning));
                    const resetVehicles = state.vehicles.map(vehicle => state.planningVehicleBackups[vehicle.id] || vehicle);
                    const backups: Record<number, Vehicle> = {};
                    const assignedIds = new Set<number>();
                    const nextVehicles = resetVehicles.map(vehicle => {
                        const assigned = (plan.vehicles || []).find((item:any) => String(item.id)===String(vehicle.id) || (item.label != null && item.label===vehicle.label));
                        if (!assigned) return vehicle;
                        assignedIds.add(vehicle.id);
                        backups[vehicle.id] = vehicle;
                        return {...vehicle,status:'assigned' as const,is_available:false,current_location:source,
                            current_position:path[0] || vehicle.current_position,capacity:assigned.capacity ?? vehicle.capacity,
                            assigned_route:{route_id:routeId,route_data:route.routeData,waypoints:[source,destination],source,destination,
                                intermediate_locations:route.intermediates,assigned_at:new Date().toISOString(),vehicle_type:vehicle.type, assigned_load_kg:assigned.assigned_load_kg, utilization_percentage:assigned.utilization_percentage,
                                vehicle_details:{...(vehicle.vehicle_details || {}),capacity:String(assigned.capacity || vehicle.capacity || '')},
                                route_cost:String(plan.operational_cost),distance:plan.distance_km}};
                    });
                    const plannedPlanes = nextVehicles.filter(vehicle => path.length >= 2 && assignedIds.has(vehicle.id) && String(vehicle.type).toLowerCase()==='plane')
                        .map(vehicle => ({id:`planning-${vehicle.id}`,routeId,sourceAirport:{...path[0],name:source},
                            destAirport:{...path[path.length - 1],name:destination},currentPosition:path[0],status:'flying' as const}));
                    return {selectedPlan:plan, planComparison:comparison, planNotice:path.length < 2 ? 'Route coordinates unavailable.' : !continuousJourney(plan) ? 'Journey playback unavailable — route geometry is incomplete or disconnected.' : null, warehouseFocus:null,
                        planningVehicleBackups:backups, activeRoutes:{...retainedRoutes,[routeId]:route},vehicles:nextVehicles,
                        activePlanes:[...state.activePlanes.filter(plane => !plane.id.startsWith('planning-')),...plannedPlanes],
                        lastCreatedRouteId:routeId,lastAssignedRouteId:routeId};
                });
                return routeId;
            },
            updateVehicle: (updatedVehicle) =>
                set((state) => ({
                    vehicles: state.vehicles.map((v) =>
                        v.id === updatedVehicle.id ? updatedVehicle : v
                    ),
                })),

            markVehicleCompleted: (vehicleId, destination, finalPosition) =>
                set((state) => ({
                    vehicles: state.vehicles.map((v) =>
                        v.id === vehicleId
                            ? {
                                ...v,
                                status: 'completed' as const,
                                current_location: destination,
                                current_position: finalPosition  // Change status to completed
                                // Keep assigned_route so marker stays visible
                            }
                            : v
                    ),
                })),

            addActiveRoute: (route) =>
                set((state) => ({
                    activeRoutes: { ...state.activeRoutes, [route.id]: route },
                })),
            updateActiveRoute: (routeId, route) =>
                set((state) => ({
                    activeRoutes: { ...state.activeRoutes, [routeId]: route },
                })),
            markRouteAsInactive: (routeId) =>
                set((state) => {
                    const route = state.activeRoutes[routeId];
                    if (route) {
                        return {
                            activeRoutes: {
                                ...state.activeRoutes,
                                [routeId]: { ...route, isActive: false }
                            }
                        };
                    }
                    return state;
                }),
            updateActiveRouteStatus: (routeId, isActive) =>
                set((state) => {
                    const route = state.activeRoutes[routeId];
                    if (route) {
                        return {
                            activeRoutes: {
                                ...state.activeRoutes,
                                [routeId]: { ...route, isActive }
                            }
                        };
                    }
                    return state;
                }),
            removeActiveRoute: (routeId) =>
                set((state) => {
                    const newActiveRoutes = { ...state.activeRoutes };

                    // Delete using both string and number representations
                    const strKey = String(routeId);
                    const numKey = Number(routeId);

                    delete (newActiveRoutes as any)[strKey];
                    delete newActiveRoutes[numKey];

                    console.log(`Removed route ${routeId}, remaining routes:`, Object.keys(newActiveRoutes));

                    return { activeRoutes: newActiveRoutes };
                }),
            clearActiveRoutes: () => set({ activeRoutes: {} }),
            setActiveRoutes: (routes) => set({ activeRoutes: routes }),

            addChatMessage: (role, content) =>
                set((state) => ({
                    chatHistory: [
                        ...state.chatHistory,
                        { role, content, timestamp: Date.now() },
                    ],
                })),
            clearChatHistory: () => set({ chatHistory: [] }),
            setChatHistory: (messages) => set({
                chatHistory: messages.map(msg => ({
                    role: msg.role,
                    content: msg.content,
                    timestamp: Date.now()
                }))
            }),

            addPlane: (plane) => set((state) => ({
                activePlanes: [...state.activePlanes, plane]
            })),
            updatePlane: (id, updates) => set((state) => ({
                activePlanes: state.activePlanes.map(p =>
                    p.id === id ? { ...p, ...updates } : p
                )
            })),
            removePlane: (id) => set((state) => ({
                activePlanes: state.activePlanes.filter(p => p.id !== id)
            })),

            setLoading: (isLoading) => set({ isLoading }),
            toggleDashboard: () =>
                set((state) => ({ isDashboardOpen: !state.isDashboardOpen })),
            setSelectedVehicle: (id) => set({ selectedVehicleId: id }),
            setMapViewMode: (mode) => set({ mapViewMode: mode }),
            setHasCsvUploaded: (value) => set({ hasCsvUploaded: value }),
            setActiveDashboard: (dashboard) => set({ activeDashboard: dashboard }),
            setLastAssignedRouteId: (routeId) => set({ lastAssignedRouteId: routeId }),
            setLastCreatedRouteId: (routeId) => set({ lastCreatedRouteId: routeId }),
            setHighlightedRouteIds: (routeIds) => set({ highlightedRouteIds: routeIds }),
            setSegmentSession: (session) => set({ segmentSession: session }),
            setOnSegmentComplete: (callback) => { _onSegmentComplete = callback; },
            setPendingVehiclesCount: (count) => set({ pendingVehiclesCount: count }),
            decrementPendingVehicles: () => {
                let shouldCallComplete = false;
                set((state) => {
                    const newCount = Math.max(0, state.pendingVehiclesCount - 1);
                    if (newCount === 0 && _onSegmentComplete) {
                        shouldCallComplete = true;
                    }
                    return { pendingVehiclesCount: newCount };
                });
                if (shouldCallComplete && _onSegmentComplete) {
                    const cb = _onSegmentComplete;
                    _onSegmentComplete = null; // clear before calling to prevent double-fire
                    setTimeout(cb, 0);
                }
            },

            resetStore: () => {
                _onSegmentComplete = null;
                set({
                    selectedPlan:null, planComparison:null, planNotice:null, warehouseFocus:null, planningVehicleBackups:{},
                    lastCreatedRouteId:null, lastAssignedRouteId:null,
                    warehouses: [],
                    vehicles: [],
                    activeRoutes: {},
                    chatHistory: [],
                    isLoading: false,
                    isDashboardOpen: true,
                    selectedVehicleId: null,
                    mapViewMode: 'street',
                    warehouseInventory: [],
                    activePlanes: [],
                    segmentSession: null,
                    pendingVehiclesCount: 0,
                    //hasCsvUploaded: false
                });
            },
        }),

        {
            name: 'intellifleet-storage',
            partialize: (state) => ({
                mapViewMode: state.mapViewMode,
                hasCsvUploaded: state.hasCsvUploaded,
            }),


        }
    )
);
