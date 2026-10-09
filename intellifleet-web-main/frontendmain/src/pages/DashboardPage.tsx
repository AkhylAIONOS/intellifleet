import { useEffect, useState } from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {WorkspaceSplitLayout} from '../components/PlanningSplit';
import {ResizablePane} from '../components/ResizablePane';
import {controlTowerApi,type TowerRun} from '../api/controlTower';
import {useControlTowerStore} from '../store/controlTowerStore';
import {serviceToday} from '../components/LiveOperations';
import {OperationalMap} from '../components/OperationalMap';
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
import { LiveOperations } from '../components/LiveOperations';
import { NetworkUpload } from '../components/NetworkUpload';
import { FedExPanel } from '../components/FedExPanel';
import { RouteDashboard } from '../components/RouteDashboard';

export const DashboardPage = () => {
  const location=useLocation(),navigate=useNavigate();
  const workspace=location.pathname==='/planning'?'PLANNING':location.pathname==='/live-operations'?'LIVE OPERATIONS':'DASHBOARD';
  const section=new URLSearchParams(location.search).get('section')||'planner';
  const [chatOpen,setChatOpen]=useState(new URLSearchParams(location.search).get('chat')==='open'),[chatCollapsed,setChatCollapsed]=useState(false);
  useEffect(()=>{setChatOpen(workspace==='DASHBOARD'&&new URLSearchParams(location.search).get('chat')==='open');setChatCollapsed(false);},[workspace]);
  const [layoutVersion,setLayoutVersion]=useState(0);
  const [operations,setOperations]=useState<TowerRun[]>([]);
  useEffect(()=>{if(workspace==='DASHBOARD')void controlTowerApi.allRuns(serviceToday()).then(setOperations).catch(()=>setOperations([]));},[workspace]);
  useEffect(()=>{useControlTowerStore.getState().setWorkspace(workspace);},[workspace]);
  const [fedexLoaded, setFedexLoaded] = useState(false);
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
        const response = await warehouseApi.getInventory();
        if (response.data.inventory.length > 0) {
          setWarehouseInventory(response.data.inventory);
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
        const response = await warehousesApi.getWarehouses();
        if (response.warehouses && response.warehouses.length > 0) {
          // Map warehouse_id to id for frontend compatibility
          const mappedWarehouses = response.warehouses.map((w: any) => ({
            ...w,
            id: w.warehouse_id  // Map warehouse_id to id
          }));
          setWarehouses(mappedWarehouses);
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
    useControlTowerStore.getState().setChatSessionId(null);
    void chatApi.clearChat().catch(error => console.warn('Unable to reset chat on load:', error));
  }, [clearChatHistory]);

  // Fetch route session from API on mount (for cross-device sync)
  useEffect(() => {
    const fetchRouteSession = async () => {
      try {
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
        }
      } catch (error) {
      }
    };

    fetchRouteSession();
  }, [setActiveRoutes]);

  // Fetch vehicles from API on mount (for cross-device sync)
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        const response = await vehiclesApi.getVehicles();
        if (response.vehicles && response.vehicles.length > 0) {
          setVehicles(response.vehicles);
        }
      } catch (error) {
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
    useControlTowerStore.getState().reset();

    // 2. Clear Auth (tokens/user info)
    clearAuth();

    // 3. Clear any persisted storage (optional, but good for cleanup)
    if (currentUser) {
      localStorage.removeItem(`intellifleet-storage-${currentUser.id || currentUser.email}`);
    }

    // 4. Redirect to login
    window.location.href = '/login';
  };

  const chatDrawer=chatOpen&&!chatCollapsed?<div className="planning-chat-drawer workspace-chat-drawer"><ResizablePane side="left" label="AI Chat" storageKey="unifleet-planning-chat-width" initial={380} min={280} max={560}><div className="dashboard-left"><div className="chat-shell-controls"><span>AI Chat</span><button onClick={()=>setChatCollapsed(true)}>Collapse AI</button><button onClick={()=>setChatOpen(false)}>Close AI</button><button onClick={()=>{['unifleet-chat-width','unifleet-run-details','unifleet-operations-map','unifleet-planning-map'].forEach(key=>localStorage.removeItem(key));setLayoutVersion(v=>v+1);}}>Reset layout</button></div><ChatPanel workspace={workspace==='PLANNING'&&section==='schedules'?'SCHEDULES':workspace}/></div></ResizablePane></div>:undefined;

  return (
    <div className="dashboard-container">
      <aside className="primary-sidebar"><div className="brand"><h1>UniFleet</h1><span>PLANNING & OPERATIONS</span></div><nav aria-label="Main navigation">{[['Dashboard','/dashboard'],['AI Chat','chat'],['Planning','/planning'],['Live Operations','/live-operations']].map(([label,path])=><button key={label} aria-pressed={path==='chat'?chatOpen:location.pathname===path} onClick={()=>{if(path==='chat'){setChatOpen(true);setChatCollapsed(false);}else navigate(path);}}>{label}</button>)}</nav><div className="sidebar-footer">Network planning<br/>Operations workspace</div></aside>
      <div className="application-shell"><header className="dashboard-header-bar"><strong>{workspace==='DASHBOARD'?'Command Center':workspace==='PLANNING'?'Planning':'Live Operations'}</strong><div className="user-info"><button className="add-routes-button" onClick={()=>navigate('/planning?section=network')}>Network</button><div className="user-profile-pill"><span className="user-name">{user?.name || [user?.first_name,user?.last_name].filter(Boolean).join(' ') || 'User'}</span><span className="user-plan">{user?.email}</span></div><button onClick={handleLogout} className="logout-button">Logout</button></div></header>
      <main className="dashboard-main"><div className="dashboard-right">
       {workspace==='DASHBOARD'&&<WorkspaceSplitLayout label="dashboard" storageKey="unifleet-dashboard-split" overlay={chatDrawer} left={<div className="dashboard-content workspace-scroll"><header className="workspace-heading"><div><span className="eyebrow">UNIFLEET COMMAND CENTER</span><h2>Network & operations overview</h2><p>Planning resources and imported operational runs</p></div><button onClick={()=>navigate('/live-operations')}>Open Live Operations</button></header><MapMetrics/><NetworkUpload compact/><section className="dashboard-run-summary"><div><h3>Operational attention</h3><p>{operations.length?`${operations.length} imported runs · ${operations.filter(r=>['DELAYED','EXPECTED DELAY'].includes(r.status)).length} delayed or expected delay`:'No operational runs loaded for today. Import the supplied schedule workbook in Live Operations.'}</p>{operations.filter(r=>r.critical||['DELAYED','EXPECTED DELAY'].includes(r.status)).slice(0,5).map(r=><button key={r.run_id} onClick={()=>{useControlTowerStore.getState().select(r);navigate('/live-operations');}}>{r.schedule.lane} · {r.schedule.mode} · {r.status}</button>)}</div><div><h3>AI workspace</h3><p>Ask about planning alternatives, operational status or a selected run. Answers use source schedules and calculated operational metrics.</p><button onClick={()=>{setChatOpen(true);setChatCollapsed(false);}}>Open AI Chat</button></div></section></div>} right={<div className="map-workspace">{operations.length?<OperationalMap runs={operations}/>:<MapView/>}</div>}/>}
       <div hidden={workspace!=='PLANNING'} className="planning-workspace"><nav className="planning-tabs" aria-label="Planning sections">{[['planner','Planner'],['schedules','Schedules'],['network','Network Overview']].map(([value,label])=><button key={value} aria-pressed={section===value} onClick={()=>{navigate(`/planning?section=${value}`);if(value==='schedules')setFedexLoaded(true);}}>{label}</button>)}</nav><WorkspaceSplitLayout overlay={workspace==='PLANNING'?chatDrawer:undefined} left={<><div className="planning-content"><MapMetrics/><div hidden={section!=='planner'}><PlanningPanel recovery={new URLSearchParams(location.search).get('recovery')?{runId:new URLSearchParams(location.search).get('recovery')!,origin:new URLSearchParams(location.search).get('origin')||'',destination:new URLSearchParams(location.search).get('destination')||'',unavailable:new URLSearchParams(location.search).get('unavailable')==='true'}:undefined}/></div>{workspace==='PLANNING'&&(fedexLoaded||section==='schedules')&&<div hidden={section!=='schedules'} className="schedule-workspace"><FedExPanel/></div>}{section==='network'&&<NetworkUpload/>}</div></>} right={<div className="map-workspace"><MapView/><VehicleDashboard hideTrigger/><ActiveRoutesDashboard hideTrigger/><WarehouseDashboard hideTrigger/><VehicleInfoDashboard hideTrigger/></div>}/></div>
       {workspace==='LIVE OPERATIONS'&&<LiveOperations key={layoutVersion} chatOverlay={chatDrawer}/>}
      </div>
      {(!chatOpen||chatCollapsed)&&<button className="reopen-chat" onClick={()=>{setChatOpen(true);setChatCollapsed(false);}}>{chatCollapsed?'Expand AI Chat':'Open AI Chat'}</button>}
      </main></div>
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
  const routeCount = Object.values(activeRoutes).filter(route => route.isActive !== false && !route.routeData?.planning).length;
  const selectedPlan = useAppStore(state => state.selectedPlan);
  const assignedCount = selectedPlan ? (selectedPlan.vehicles || []).length : vehicles.filter(vehicle => vehicle.status === 'assigned' || Boolean(vehicle.assigned_route)).length;
  const setActiveDashboard = useAppStore(state => state.setActiveDashboard);
  return <div className="map-metrics" aria-label="Network metrics">
    <button onClick={()=>setActiveDashboard('activeRoutes')}><span>Services</span><strong>{routeCount}</strong></button>
    <button onClick={()=>setActiveDashboard('warehouse')}><span>Stations</span><strong>{warehouses.length}</strong></button>
    <button onClick={()=>setActiveDashboard('vehicleInfo')}><span>Resources</span><strong>{vehicles.length}</strong></button>
    <button onClick={()=>setActiveDashboard('vehicleDashboard')}><span>Assigned Vehicles</span><strong>{assignedCount}</strong></button>
  </div>;
};
