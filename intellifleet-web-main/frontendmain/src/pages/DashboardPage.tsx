import { useEffect, useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { useAppStore } from '../store/appStore';
import { warehouseApi } from '../api/warehouse';
import { ChatPanel } from '../components/ChatPanel';
import { MapView } from '../components/MapView';
import { VehicleDashboard } from '../components/VehicleDashboard'
import { WarehouseDashboard } from '../components/WarehouseDashboard';
import { warehousesApi } from '../api/warehouses';
import { routesApi } from '../api/routes';
import { vehiclesApi } from '../api/vehicles';
// Disabled: AnimatedVehicleMarker now handles animation via direct Leaflet manipulation
// import { useVehicleAnimation } from '../hooks/useVehicleAnimation';
import './Dashboard.css';
//import { RouteDashboard } from '../components/RouteDashboard';
import { ActiveRoutesDashboard } from '../components/ActiveRoutesDashboard';
import { chatApi } from '../api/chat';
import { VehicleInfoDashboard } from '../components/VehicleInfoDashboard';
import { PlanningPanel } from '../components/PlanningPanel';
import { RouteDashboard } from '../components/RouteDashboard';

export const DashboardPage = () => {
  const [showRouteSelector, setShowRouteSelector] = useState(false);
  const { user, clearAuth } = useAuthStore();
  //const { hasCsvUploaded, setWarehouseInventory, warehouseInventory } = useAppStore();
  const resetStore = useAppStore((state) => state.resetStore);

  const { setWarehouseInventory, setWarehouses, clearChatHistory, setActiveRoutes, setVehicles } = useAppStore();

  // Fetch inventory on mount if CSV was previously uploaded
  // useEffect(() => {
  //   const fetchInventoryOnLoad = async () => {
  //     if (hasCsvUploaded) {
  //       try {
  //         const response = await warehouseApi.getInventory();
  //         if (response.data && response.data.length > 0) {
  //           setWarehouseInventory(response.data);
  //         }
  //       } catch (error) {
  //         console.error('Failed to fetch inventory on load:', error);
  //       }
  //     }
  //   };

  //   fetchInventoryOnLoad();
  // }, [hasCsvUploaded, warehouseInventory.length, setWarehouseInventory]);

  // Fetch inventory on mount (for cross-device sync)
  useEffect(() => {
    const fetchInventoryOnLoad = async () => {
      try {
        console.log('Fetching inventory from API...');
        const response = await warehouseApi.getInventory();
        if (response.data.inventory.length > 0) {
          setWarehouseInventory(response.data.inventory);
          console.log('Inventory loaded:', response.data.inventory.length, 'items');
        }
      } catch (error) {
        console.error('Failed to fetch inventory on load:', error);
        // This is fine - inventory might be empty
      }
    };

    fetchInventoryOnLoad();
  }, [setWarehouseInventory]);

  // Fetch warehouses from API on mount (for cross-device sync)
  useEffect(() => {
    const fetchWarehouses = async () => {
      try {
        console.log('Fetching warehouses from API...');
        const response = await warehousesApi.getWarehouses();
        if (response.warehouses && response.warehouses.length > 0) {
          // Map warehouse_id to id for frontend compatibility
          const mappedWarehouses = response.warehouses.map((w: any) => ({
            ...w,
            id: w.warehouse_id  // Map warehouse_id to id
          }));
          setWarehouses(mappedWarehouses);
          console.log('Warehouses loaded:', mappedWarehouses.length);
        }
      } catch (error) {
        console.error('Failed to fetch warehouses:', error);
      }
    };

    fetchWarehouses();
  }, [setWarehouses]);

  // A browser load starts a fresh conversation while preserving network data.
  useEffect(() => {
    clearChatHistory();
    void chatApi.clearChat().catch(error => console.warn('Unable to reset chat on load:', error));
  }, [clearChatHistory]);

  // Fetch route session from API on mount (for cross-device sync)
  useEffect(() => {
    const fetchRouteSession = async () => {
      try {
        console.log('Fetching route session from API...');
        const response = await routesApi.getRouteSession();

        if (response.success && response.data) {
          const allRoutes: Record<number, any> = {};

          // 1. Map normal routes
          response.data.routes?.forEach((route: any) => {
            allRoutes[route.route_id] = {
              id: route.route_id,
              source: route.data?.source,
              destination: route.data?.destination,
              intermediates: route.data?.intermediate_locations || [],
              waypoints: route.data?.locations || [route.data?.source, route.data?.destination],
              created: new Date(route.created_at),
              isActive: route.is_active !== false,
              routeData: {
                route_type: route.data?.route_type,
                optimal_routes: route.data?.optimal_routes,
                //route_cost: route.data?.route_cost,
                route_cost: route.data?.route_cost ? Number(route.data.route_cost).toFixed(2) : null,
                source_coords: route.data?.source_coords,
                dest_coords: route.data?.dest_coords,
                route_id: route.route_id,
                objective: route.data?.objective || null,
                //cached: route.data?.cached !== undefined ? route.data.cached : undefined
              }
            };
          });

          // 2. Map alternative routes
          response.data.alternative_routes?.forEach((route: any) => {
            allRoutes[route.route_id] = {
              id: route.route_id,
              source: route.data?.source,
              destination: route.data?.destination,
              intermediates: route.data?.intermediate_locations || [],
              waypoints: route.data?.waypoints || [route.data?.source, route.data?.destination],
              created: new Date(route.created_at),
              isActive: route.is_active !== false,
              routeData: {
                route_type: route.data?.route_type,
                optimal_routes: [{
                  ...route.data?.alternative_route,
                  isOptimal: false
                }],
                //route_cost: route.data?.route_cost,
                route_cost: route.data?.route_cost ? Number(route.data.route_cost).toFixed(2) : null,
                reason: route.data?.reason,
                route_id: route.route_id,
                objective: route.data?.objective || null
              }
            };
          });

          // 3. Map multimodal routes
          response.data.multimodal_routes?.forEach((route: any) => {
            allRoutes[route.route_id] = {
              id: route.route_id,
              source: route.source,
              destination: route.destination,
              intermediates: [],
              waypoints: [route.source, route.destination],
              created: new Date(route.created_at),
              isActive: route.is_active !== false,
              routeData: {
                multimodal: true,
                segments: {
                  segment_1: route.multimodal_data?.segment_1,
                  segment_2: route.multimodal_data?.segment_2,
                  segment_3: route.multimodal_data?.segment_3
                },
                total_distance: route.multimodal_data?.total_distance_km,
                total_duration: route.multimodal_data?.total_duration,
                route_cost: (route.multimodal_data?.total_cost ?? route.total_cost)?.toFixed?.(2) ??
                  Number(route.multimodal_data?.total_cost ?? route.total_cost).toFixed(2),
                route_id: route.route_id,
                objective: route.multimodal_data?.objective || null,
                //cached: route.cached !== undefined ? route.cached : undefined
              }
            };
          });

          setActiveRoutes(allRoutes);
          console.log('Routes loaded:', Object.keys(allRoutes).length, 'routes');
        }
      } catch (error) {
        console.log('No route session found or failed to fetch:', error);
      }
    };

    fetchRouteSession();
  }, [setActiveRoutes]);

  // Fetch vehicles from API on mount (for cross-device sync)
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        console.log('Fetching vehicles from API...');
        const response = await vehiclesApi.getVehicles();
        if (response.vehicles && response.vehicles.length > 0) {
          setVehicles(response.vehicles);
          console.log('Vehicles loaded:', response.vehicles.length);
        }
      } catch (error) {
        console.log('Failed to fetch vehicles:', error);
      }
    };

    fetchVehicles();
  }, [setVehicles]);

  // Animation is now handled directly in AnimatedVehicleMarker via Leaflet API
  // useVehicleAnimation();

  // const handleLogout = () => {
  //   const currentUser = useAuthStore.getState().user;
  //   const userStorageKey = `intellifleet-storage-${currentUser?.id || currentUser?.email}`;

  //   // Save current state for this user
  //   const currentState = useAppStore.getState();
  //   localStorage.setItem(userStorageKey, JSON.stringify({
  //     warehouses: currentState.warehouses,
  //     vehicles: currentState.vehicles,
  //     activeRoutes: currentState.activeRoutes,
  //     chatHistory: currentState.chatHistory,
  //     hasCsvUploaded: currentState.hasCsvUploaded,
  //   }));

  //   resetStore();  // Clear the active state
  //   clearAuth();
  //   window.location.href = '/login';
  // };

  const handleLogout = async () => {
    const currentUser = useAuthStore.getState().user;
    // Standard Production Logout:
    // 1. Clear Zustand store (memory)
    await chatApi.clearChat().catch(() => undefined);
    resetStore();

    // 2. Clear Auth (tokens/user info)
    clearAuth();

    // 3. Clear any persisted storage (optional, but good for cleanup)
    if (currentUser) {
      localStorage.removeItem(`intellifleet-storage-${currentUser.id || currentUser.email}`);
    }

    // 4. Redirect to login
    window.location.href = '/login';
  };

  return (
    <div className="dashboard-container">
      <header className="dashboard-header-bar">
        <div className="brand">
          <h1>UniFleet</h1>
        </div>
        <div className="user-info">
          <button className="add-routes-button" aria-expanded={showRouteSelector} onClick={() => setShowRouteSelector(value => !value)}>
            + Add Route
          </button>
          <div className="user-profile-pill">
            <span className="user-name">👋 {user?.first_name || 'User'}</span>
            <span className="user-plan">Premium</span>
          </div>
          <button onClick={handleLogout} className="logout-button">
            Logout
          </button>
        </div>
      </header>
      <main className="dashboard-main">
        <div className="dashboard-left">
          <ChatPanel />
        </div>
        <div className="dashboard-right">
          <PlanningPanel />
          <div className="map-workspace">
            <MapView />
            <MapMetrics />
            <VehicleDashboard hideTrigger />
            <ActiveRoutesDashboard hideTrigger />
            <WarehouseDashboard hideTrigger />
            <VehicleInfoDashboard hideTrigger />
          </div>
        </div>
      </main>
      {showRouteSelector && (
        <div className="route-selector-backdrop" role="presentation" onMouseDown={() => setShowRouteSelector(false)}>
          <div className="route-selector-dialog" role="dialog" aria-modal="true" aria-label="Route management" onMouseDown={event => event.stopPropagation()}>
            <RouteDashboard onClose={() => setShowRouteSelector(false)} />
          </div>
        </div>
      )}
    </div>
  );
};

const MapMetrics = () => {
  const warehouses = useAppStore(state => state.warehouses);
  const vehicles = useAppStore(state => state.vehicles);
  const activeRoutes = useAppStore(state => state.activeRoutes);
  const routeCount = Object.values(activeRoutes).filter(route => route.isActive !== false).length;
  const selectedPlan = useAppStore(state => state.selectedPlan);
  const assignedCount = selectedPlan ? (selectedPlan.vehicles || []).length : vehicles.filter(vehicle => vehicle.status === 'assigned' || Boolean(vehicle.assigned_route)).length;
  const setActiveDashboard = useAppStore(state => state.setActiveDashboard);
  return <div className="map-metrics" aria-label="Network metrics">
    <button onClick={()=>setActiveDashboard('activeRoutes')}><span>Active Routes</span><strong>{routeCount}</strong></button>
    <button onClick={()=>setActiveDashboard('warehouse')}><span>Warehouses</span><strong>{warehouses.length}</strong></button>
    <button onClick={()=>setActiveDashboard('vehicleInfo')}><span>Vehicles</span><strong>{vehicles.length}</strong></button>
    <button onClick={()=>setActiveDashboard('vehicleDashboard')}><span>Assigned Vehicles</span><strong>{assignedCount}</strong></button>
  </div>;
};
