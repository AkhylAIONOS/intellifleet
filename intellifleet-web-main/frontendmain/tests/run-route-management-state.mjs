import { createServer } from 'vite';
const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
try{
 const {filterRoutes,routeMode}=await server.ssrLoadModule('/src/components/RouteDashboard.tsx');
 const routes=[{id:1,source:'IF Delhi NCR Mega Hub',destination:'IF Mumbai West Hub',routeData:{route_type:'GROUND'}},{id:2,source:'IF Delhi NCR Mega Hub',destination:'IF Frankfurt Gateway',routeData:{route_type:'Express',distance:6120,duration:9,route_cost:420000}},{id:3,source:'overlay',destination:'overlay',routeData:{planning:true,legs:[{route_type:'air'}]}}];
 const all=filterRoutes(routes,'','all'),road=filterRoutes(routes,'','road'),air=filterRoutes(routes,'','air');
 const byId=filterRoutes(routes,'2','air'),byLocation=filterRoutes(routes,'Mumbai','road'),selected=air[0];
 const pass=all.length===2&&road.length===1&&air.length===1&&byId.length===1&&byLocation.length===1&&routeMode(road[0])==='road'&&routeMode(selected)==='air'&&selected.source&&selected.destination&&selected.routeData.distance===6120;
 console.log(JSON.stringify({route_management_state:pass,all:all.length,road:road.length,air:air.length,search_with_filter:byId.length===1,air_selection:Boolean(selected?.source&&selected?.destination),overlay_excluded:!all.some(route=>route.routeData?.planning)}));
 if(!pass)process.exitCode=1;
}finally{await server.close()}
