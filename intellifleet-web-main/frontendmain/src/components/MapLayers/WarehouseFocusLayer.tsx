import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { useAppStore } from '../../store/appStore';
import { validPoint } from '../../utils/planVisuals';
export function WarehouseFocusLayer() {
  const map = useMap();
  const focus = useAppStore(s=>s.warehouseFocus);
  const warehouses = useAppStore(s=>s.warehouses);
  useEffect(() => {
    if (!focus) return;
    const warehouse = warehouses.find(w => focus.warehouse_id != null ? String(w.warehouse_id ?? w.id) === String(focus.warehouse_id) : w.name === focus.warehouse);
    const point = {lat:focus.latitude ?? warehouse?.latitude, lng:focus.longitude ?? warehouse?.longitude};
    if (!validPoint(point)) return;
    const popup = document.createElement('div'); popup.className='journey-popup';
    const title = document.createElement('strong'); title.textContent=focus.warehouse || warehouse?.name || 'Warehouse'; popup.append(title);
    for (const [label,value,unit] of [['Inventory',focus.current_inventory,''],['Available',focus.available_inventory,''],
      ['Free storage',focus.available_storage,''],['Utilization',focus.utilization_percentage,'%']] as const) {
      if (value == null) continue;
      const row=document.createElement('div'); row.textContent=`${label}: ${value.toLocaleString('en-IN')}${unit}`; popup.append(row);
    }
    const marker=L.marker(point,{icon:L.divIcon({className:'warehouse-selected warehouse-emphasis',html:'▣',iconSize:[32,32],iconAnchor:[16,16]}),zIndexOffset:1000}).addTo(map);
    marker.bindPopup(popup,{maxWidth:250,autoPan:false});
    map.stop(); map.setView(point,12,{animate:!window.matchMedia('(prefers-reduced-motion: reduce)').matches});
    marker.openPopup();
    const timeout=window.setTimeout(()=>marker.getElement()?.classList.remove('warehouse-emphasis'),12000);
    return () => { window.clearTimeout(timeout); marker.remove(); };
  },[map,focus,warehouses]);
  return null;
}
