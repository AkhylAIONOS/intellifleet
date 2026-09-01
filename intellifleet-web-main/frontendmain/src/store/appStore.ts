import { create } from 'zustand';
import { persist } from 'zustand/middleware';
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

    // Reset
    resetStore: () => void;
}

export const useAppStore = create<AppState>()(
    persist(
        (set) => ({
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
