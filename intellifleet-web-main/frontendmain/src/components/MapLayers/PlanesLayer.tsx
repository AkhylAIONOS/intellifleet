import { useAppStore } from '../../store/appStore';
import { PlaneMarker } from './PlaneMarker';

export const PlanesLayer = () => {
    const activePlanes = useAppStore(state => state.activePlanes);

    // Only render flying or landed planes (not removed)
    const visiblePlanes = activePlanes.filter(p => p.status !== 'removed');

    return (
        <>
            {visiblePlanes.map(plane => (
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