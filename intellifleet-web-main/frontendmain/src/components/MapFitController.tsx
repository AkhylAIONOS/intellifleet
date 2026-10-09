import {useEffect} from 'react';
import {useMap} from 'react-leaflet';
import L from 'leaflet';
export function MapFitController({points}:{points:[number,number][]}){
 const map=useMap();
 useEffect(()=>{const workspace=map.getContainer().closest('.dockable-workspace');const fit=()=>{if(points.length)map.fitBounds(L.latLngBounds(points),{padding:[32,32],maxZoom:10,animate:false});};workspace?.addEventListener('unifleet:fit-map',fit);return()=>workspace?.removeEventListener('unifleet:fit-map',fit);},[map,points]);
 return null;
}
