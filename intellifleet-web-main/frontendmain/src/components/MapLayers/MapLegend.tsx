import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { useAppStore } from '../../store/appStore';
export function MapLegend() {
  const map=useMap(), plan=useAppStore(s=>s.selectedPlan), routes=useAppStore(s=>s.activeRoutes), warehouses=useAppStore(s=>s.warehouses);
  useEffect(()=>{
    const rows:string[]=[];
    const network=Object.values(routes).filter(route=>!route.routeData?.planning);
    if(network.length)rows.push('<span><i></i>Base Network</span>');
    if(plan)rows.push('<span><i class="selected"></i>Selected Plan</span>');
    if(network.some(route=>route.routeData?.optimal_routes?.[0]?.isOptimal===false))rows.push('<span><i class="alternative"></i>Alternative</span>');
    if(plan?.route_legs.some(leg=>leg.route_type==='road'))rows.push('<span>🚚 Ground</span>');
    if(plan?.route_legs.some(leg=>leg.route_type==='air'))rows.push('<span>✈ Air</span>');
    if(warehouses.length)rows.push('<span>▣ Warehouse</span>');
    if(!rows.length)return;
    const control=new L.Control({position:'bottomright'});
    control.onAdd=()=>{const el=L.DomUtil.create('div','plan-map-legend');el.innerHTML=rows.join('');return el;};
    control.addTo(map);return()=>{control.remove();};
  },[map,plan,routes,warehouses]);
  return null;
}
