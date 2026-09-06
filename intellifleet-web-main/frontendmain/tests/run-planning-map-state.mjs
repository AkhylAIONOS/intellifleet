import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
try {
  const { useAppStore } = await server.ssrLoadModule('/src/store/appStore.ts');
  const store = useAppStore.getState();
  store.resetStore();
  store.setVehicles([
    {id:11006,label:'TRK-002',type:'truck',warehouse_id:1,current_location:'Delhi',current_position:{lat:28.5355,lng:77.271},is_available:true,status:'available'},
    {id:11026,label:'AIR-002',type:'Plane',warehouse_id:1,current_location:'Delhi',current_position:{lat:28.5562,lng:77.1},is_available:true,status:'available'},
  ]);
  const result=(id,mode,vehicle,from,to,start,end)=>({planning_request:{source:from,destination:to},recommended_plan:{plan_id:id,mode,
    route_legs:[{route_id:mode==='road'?5:25,from_location:from,to_location:to,route_type:mode,source_coords:start,destination_coords:end}],
    distance_km:1400,duration_hours:mode==='road'?19.67:3.5,operational_cost:mode==='road'?349155:500000,vehicles:[vehicle]}});
  store.applyPlanningMapPlan(result('road-plan','road',{id:11006,label:'TRK-002',capacity:7000},'IF Delhi NCR Mega Hub','IF Mumbai West Hub',{lat:28.5355,lng:77.271},{lat:19.1136,lng:72.8697}));
  let state=useAppStore.getState();
  const roadRoute=Object.values(state.activeRoutes)[0];
  const roadPass=Object.keys(state.activeRoutes).length===1 && roadRoute.routeData.legs[0].route_type==='road' &&
    state.vehicles.find(v=>v.id===11006)?.assigned_route?.route_id===roadRoute.id && state.lastCreatedRouteId===roadRoute.id;
  store.applyPlanningMapPlan(result('air-plan','air',{id:11026,label:'AIR-002',capacity:10000},'IF Delhi NCR Mega Hub','IF Mumbai West Hub',{lat:28.5562,lng:77.1},{lat:19.0896,lng:72.8656}));
  state=useAppStore.getState();
  const airRoute=Object.values(state.activeRoutes)[0];
  const airPass=Object.keys(state.activeRoutes).length===1 && airRoute.routeData.legs[0].route_type==='air' &&
    state.vehicles.find(v=>v.id===11026)?.assigned_route?.route_id===airRoute.id && state.activePlanes.some(p=>p.routeId===airRoute.id);
  const staleCleared=state.vehicles.find(v=>v.id===11006)?.status==='available' && !state.vehicles.find(v=>v.id===11006)?.assigned_route;
  store.applyPlanningMapPlan(result('replanned-road','road',{id:11006,label:'TRK-002',capacity:7000},'IF Delhi NCR Mega Hub','IF Mumbai West Hub',{lat:28.5355,lng:77.271},{lat:19.1136,lng:72.8697}));
  state=useAppStore.getState();
  const replanRoute=Object.values(state.activeRoutes)[0];
  const disruptionReplacement=Object.keys(state.activeRoutes).length===1 && replanRoute.routeData.plan_id==='replanned-road' &&
    state.vehicles.find(v=>v.id===11006)?.assigned_route?.route_id===replanRoute.id && state.vehicles.find(v=>v.id===11026)?.status==='available';
  console.log(JSON.stringify({road_map_state:roadPass,air_map_state:airPass,road_to_air_replacement:staleCleared,
    disruption_map_replacement:disruptionReplacement,active_route_count:Object.keys(state.activeRoutes).length}));
  if (!roadPass || !airPass || !staleCleared || !disruptionReplacement) process.exitCode=1;
} finally { await server.close(); }
