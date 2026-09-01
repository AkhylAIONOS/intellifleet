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
import { RouteUploadTable } from '../components/RouteUploadTable';
// Disabled: AnimatedVehicleMarker now handles animation via direct Leaflet manipulation
// import { useVehicleAnimation } from '../hooks/useVehicleAnimation';
import './Dashboard.css';
//import { RouteDashboard } from '../components/RouteDashboard';
import { ActiveRoutesDashboard } from '../components/ActiveRoutesDashboard';
import { chatApi } from '../api/chat';
import { VehicleInfoDashboard } from '../components/VehicleInfoDashboard';

export const DashboardPage = () => {
  const { user, clearAuth } = useAuthStore();
  //const { hasCsvUploaded, setWarehouseInventory, warehouseInventory } = useAppStore();
  const resetStore = useAppStore((state) => state.resetStore);

  const { setWarehouseInventory, setWarehouses, setChatHistory, chatHistory, setActiveRoutes, setVehicles } = useAppStore();
  const [isRouteTableOpen, setIsRouteTableOpen] = useState(false);

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
        if (response.data && response.data.length > 0) {
          setWarehouseInventory(response.data);
          console.log('Inventory loaded:', response.data.length, 'items');
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

  // Fetch chat history from API on mount (for cross-device sync)
  useEffect(() => {
    const fetchChatHistory = async () => {
      try {
        console.log('Fetching chat history from API...');
        const response = await chatApi.getChatHistory();
        if (response.success === true && response.data && response.data.length > 0) {
          setChatHistory(response.data);
          console.log('Chat history loaded:', response.data.length, 'messages');
        }
        // If history is empty, the welcome message in ChatPanel will show automatically
      } catch (error) {
        console.log('No chat history found or failed to fetch:', error);
        // This is fine - welcome message will show
      }
    };

    // Only fetch if chatHistory is empty (to avoid overwriting local changes)
    if (chatHistory.length === 0) {
      fetchChatHistory();
    }
  }, [setChatHistory, chatHistory.length]);

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

  const handleLogout = () => {
    // Standard Production Logout:
    // 1. Clear Zustand store (memory)
    resetStore();

    // 2. Clear Auth (tokens/user info)
    clearAuth();

    // 3. Clear any persisted storage (optional, but good for cleanup)
    const currentUser = useAuthStore.getState().user;
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
          <div className="sample-downloads">
            <a href="/sample_warehouse_data.csv" download="sample_warehouse_data.csv" className="download-pill" title="Download Sample Warehouse CSV">
              ⬇ Warehouse CSV
            </a>
            <a href="/sample_vehicle_data.csv" download="sample_vehicle_data.csv" className="download-pill" title="Download Sample Vehicle CSV">
              ⬇ Vehicle CSV
            </a>
            <a href="/routes.csv" download="routes.csv" className="download-pill" title="Download Sample Routes CSV">
              ⬇ Routes CSV
            </a>
            <button
              className="download-pill"
              onClick={() => setIsRouteTableOpen(true)}
              title="Add Routes via Table"
            >
              📋 Add Routes
            </button>
          </div>
          <div className="user-profile-pill">
            <span className="user-name">👋 {user?.first_name || 'User'}</span>
            <span className="user-plan">Freemium</span>
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
          <MapView />
          <VehicleDashboard />
          {/* <RouteDashboard /> */}
          <ActiveRoutesDashboard />
          <WarehouseDashboard />
          <VehicleInfoDashboard />
        </div>
        <RouteUploadTable
          isOpen={isRouteTableOpen}
          onClose={() => setIsRouteTableOpen(false)}
        />


      </main>
    </div>
  );
};

