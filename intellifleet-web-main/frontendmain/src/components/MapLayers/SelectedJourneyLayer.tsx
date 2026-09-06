import { useEffect, useMemo, useRef, useState } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { useAppStore } from '../../store/appStore';
import { normalizeVisualPlan, validPoint, continuousJourney, legPoints, type Assignment } from '../../utils/planVisuals';
import { playJourney } from '../../utils/journeyPlayback';
import '../PlanVisuals.css';

const icon = (air: boolean, count = 1) => L.divIcon({className:'journey-vehicle', html:`${air ? '✈' : '🚚'}${count > 1 ? `<small>${count}</small>` : ''}`, iconSize:[34,34],iconAnchor:[17,17]});
const groundIcon = icon(false), airIcon = icon(true);
const isAir = (mode?: string) => ['air','plane','aircraft'].includes(String(mode).toLowerCase());
function vehiclePopup(vehicles: Assignment[], mode: string) {
  const card = document.createElement('div');
  card.className = 'journey-popup';
  for (const v of vehicles) {
    const heading = document.createElement('strong'); heading.textContent = `${v.label || v.id} · ${v.type || mode}`; card.append(heading);
    for (const [label, value, unit] of [['Capacity',v.capacity,'kg'],['Assigned load',v.assigned_load_kg,'kg'],['Utilization',v.utilization_percentage,'%']] as const) {
      if (value == null) continue;
      const row = document.createElement('div'); row.textContent = `${label}: ${value.toLocaleString('en-IN', {maximumFractionDigits:6})} ${unit}`; card.append(row);
    }
  }
  const note = document.createElement('small'); note.textContent = 'Visual demo · not live tracking'; card.append(note);
  return card;
}
export function SelectedJourneyLayer() {
  const map = useMap();
  const selectedPlan = useAppStore(s => s.selectedPlan);
  const plan = useMemo(() => selectedPlan ? normalizeVisualPlan(selectedPlan) : null, [selectedPlan]);
  const [failure, setFailure] = useState<Error | null>(null);
  const warehouseFocus = useAppStore(s => s.warehouseFocus);
  const [replay, setReplay] = useState(0);
  const followRef = useRef(true);
  useEffect(() => { if (warehouseFocus) followRef.current = false; }, [warehouseFocus]);
  useEffect(() => {
    if (!plan) return;
    const group = L.layerGroup().addTo(map);
    let dispose = () => { group.remove(); };
    try {
    const points = plan.route_legs.flatMap(legPoints);
    if (points.length < 2) return () => { group.remove(); };
    const pane = map.getPane('selectedJourney') || map.createPane('selectedJourney');
    pane.style.zIndex = '450';
    plan.route_legs.forEach(leg => {
      const path = legPoints(leg);
      if (path.length < 2) return;
      L.polyline(path, {pane:'selectedJourney', color:'#fff',weight:10,opacity:.9,interactive:false}).addTo(group);
      const line = L.polyline(path, {pane:'selectedJourney',color:leg.disrupted || leg.is_active === false ? '#dc2626' : '#2563eb',weight:6,opacity:1}).addTo(group);
      const text = document.createElement('div'); text.textContent = `${leg.from_location} → ${leg.to_location} · ${leg.route_type}`;
      line.bindPopup(text);
    });
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    // Fit first. Keep zoom fixed during playback and follow only near viewport edges.
    map.stop();
    map.fitBounds(L.latLngBounds(points), {padding:[65,65],maxZoom:10,animate:false});
    followRef.current = true;
    const stopFollow = () => { followRef.current = false; map.stop(); };
    const container = map.getContainer();
    container.addEventListener('pointerdown', stopFollow);
    container.addEventListener('wheel', stopFollow, {passive:true});
    container.addEventListener('keydown', stopFollow);
    map.on('dragstart', stopFollow);
    const assignments = Array.isArray(plan.leg_assignments) ? plan.leg_assignments.flatMap(segment =>
      (segment.route_legs || []).flatMap(leg => (segment.vehicles || []).map(vehicle => ({...vehicle, route_id:leg.route_id})))) : plan.vehicles || [];
    // Multiple assignments on the same path share a marker and list every exact assignment.
    // For mixed mode plans the marker shows only vehicles compatible with the active leg.
    const marker = assignments.length ? L.marker(points[0], {icon:isAir(plan.route_legs[0]?.route_type) ? airIcon : groundIcon,zIndexOffset:900}).addTo(group) : null;
    let previousLeg = -1;
    let lastPan = 0;
    let cancel = () => {};
    const motionChanged = () => { cancel(); cancel = assignments.length ? start() : () => {}; };
    dispose = () => {
      cancel(); group.remove();
      if (map.getPane('mapPane')) map.stop();
      media.removeEventListener('change',motionChanged);
      container.removeEventListener('pointerdown',stopFollow);
      container.removeEventListener('wheel',stopFollow);
      container.removeEventListener('keydown',stopFollow);
      map.off('dragstart',stopFollow);
    };
    const start = () => playJourney(plan, position => {
      if (!validPoint(position)) return;
      const air = isAir(position.mode);
      const compatible = assignments.filter(v => (v.leg_index == null || v.leg_index === position.legIndex) &&
        (v.route_id == null || v.route_id === plan.route_legs[position.legIndex]?.route_id) && (!v.type || isAir(v.type) === air));
      if (marker) {
        marker.setLatLng(position);
        marker.setOpacity(compatible.length ? 1 : 0);
        if (previousLeg !== position.legIndex) {
          marker.setIcon(compatible.length > 1 ? icon(air, compatible.length) : air ? airIcon : groundIcon);
          marker.bindPopup(vehiclePopup(compatible, position.mode), {maxWidth:260});
          previousLeg = position.legIndex;
        }
      }
      const now = performance.now();
      if (followRef.current && !media.matches && now - lastPan > 450) {
        // Follow within the center range that keeps the complete journey in view.
        const zoom = map.getZoom();
        const projected = points.map(point => map.project(L.latLng(point), zoom));
        const half = map.getSize().divideBy(2).subtract(L.point(40,40));
        const desired = map.project(L.latLng(position), zoom);
        const lowX = Math.max(...projected.map(p=>p.x)) - half.x;
        const highX = Math.min(...projected.map(p=>p.x)) + half.x;
        const lowY = Math.max(...projected.map(p=>p.y)) - half.y;
        const highY = Math.min(...projected.map(p=>p.y)) + half.y;
        if (lowX <= highX && lowY <= highY) {
          const target = L.point(Math.max(lowX,Math.min(highX,desired.x)),Math.max(lowY,Math.min(highY,desired.y)));
          const center = map.unproject(target,zoom);
          if (validPoint(center)) map.panTo(center, {animate:true,duration:.45});
        }
        lastPan = now;
      }
    }, undefined, media.matches || !continuousJourney(plan), error => setFailure(error));
    cancel = assignments.length ? start() : () => {};
    media.addEventListener('change',motionChanged);
    return dispose;
    } catch (error) {
      dispose();
      throw error;
    }

  }, [map, plan, replay]);
  useEffect(() => {
    if (!plan) return;
    const control = new L.Control({position:'bottomleft'});
    control.onAdd = () => {
      const container = L.DomUtil.create('div','journey-controls');
      L.DomEvent.disableClickPropagation(container); L.DomEvent.disableScrollPropagation(container);
      const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Replay Journey';
      button.disabled = !plan.vehicles?.length || !continuousJourney(plan);
      button.onclick = () => setReplay(value => value + 1);
      const label = document.createElement('small'); label.textContent = '10-second visual demo';
      container.append(button,label); return container;
    };
    control.addTo(map); return () => { control.remove(); };
  },[map,plan]);
  if (failure) throw failure;
  return null;
}
