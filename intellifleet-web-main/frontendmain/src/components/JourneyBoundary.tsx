import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useAppStore } from '../store/appStore';
import { SelectedJourneyLayer } from './MapLayers/SelectedJourneyLayer';
import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';

export class VisualizationBoundary extends Component<{children:ReactNode; fallback:ReactNode; resetKey?:unknown}, {failed:boolean; lastResetKey:unknown}> {
  state = {failed:false,lastResetKey:undefined as unknown};
  static getDerivedStateFromProps(props:{resetKey?:unknown},state:{lastResetKey:unknown}) {
    return props.resetKey !== state.lastResetKey ? {failed:false,lastResetKey:props.resetKey} : null;
  }
  static getDerivedStateFromError() { return {failed:true}; }
  componentDidCatch(error:Error, info:ErrorInfo) { console.error('Journey visualization failed',error,info.componentStack); }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
function JourneyFallback() {
  const map=useMap();
  useEffect(()=>{
    const control=new L.Control({position:'bottomleft'});
    control.onAdd=()=>{
      const element=L.DomUtil.create('div','journey-controls');
      element.setAttribute('role','status');
      element.textContent='Journey visualization unavailable for this plan.';
      return element;
    };
    control.addTo(map);return()=>{control.remove();};
  },[map]);
  return null;
}
export function GuardedJourney() {
  const plan=useAppStore(state=>state.selectedPlan);
  // A new selection gets a fresh boundary; other dashboard components stay mounted.
  return <VisualizationBoundary resetKey={plan} fallback={<JourneyFallback/>}>
    <SelectedJourneyLayer/>
  </VisualizationBoundary>;
}
