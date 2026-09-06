import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { useAppStore } from '../../store/appStore';
import { PlaneMarker } from './PlaneMarker';

export const PlanesLayer = () => {
    const selectedPlan = useAppStore(state => state.selectedPlan);
    const activePlanes = useAppStore(state => state.activePlanes);

    // Only render flying or landed planes (not removed)
    const visiblePlanes = activePlanes.filter(p => p.status !== 'removed' && !p.id.startsWith('planning-'));

    return (
        <>
            {visiblePlanes.map(plane => selectedPlan ? (
                <Marker key={plane.id} position={plane.currentPosition} icon={L.divIcon({className:'network-plane',html:'✈',iconSize:[24,24],iconAnchor:[12,12]})}>
                    <Popup><b>{plane.id}</b><br />{plane.sourceAirport.name} → {plane.destAirport.name}</Popup>
                </Marker>
            ) : (
                <PlaneMarker
                    key={plane.id}
                    planeId={plane.id}
                    routeId={plane.routeId}
                    sourceAirport={plane.sourceAirport}
                    destAirport={plane.destAirport}
                />
            ))}
        </>
    );
};