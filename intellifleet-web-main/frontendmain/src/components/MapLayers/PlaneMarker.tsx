import { useEffect, useRef } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { useAppStore } from '../../store/appStore';
import { generateArcPath } from '../../utils/generateArcPath';

interface PlaneMarkerProps {
    planeId: string;
    routeId: number;
    sourceAirport: { lat: number; lng: number; name: string };
    destAirport: { lat: number; lng: number; name: string };
}

export const PlaneMarker = ({ planeId, routeId, sourceAirport, destAirport }: PlaneMarkerProps) => {
    const markerRef = useRef<L.Marker | null>(null);
    const requestRef = useRef<number | undefined>(undefined);
    const startTimeRef = useRef<number | undefined>(undefined);
    const pathRef = useRef<{ lat: number; lng: number }[]>([]);
    const bearingRef = useRef<number>(0);

    // Calculate bearing between two points
    const calculateBearing = (
        start: { lat: number; lng: number },
        end: { lat: number; lng: number }
    ) => {
        const startLat = (start.lat * Math.PI) / 180;
        const startLng = (start.lng * Math.PI) / 180;
        const endLat = (end.lat * Math.PI) / 180;
        const endLng = (end.lng * Math.PI) / 180;

        const dLng = endLng - startLng;
        const y = Math.sin(dLng) * Math.cos(endLat);
        const x =
            Math.cos(startLat) * Math.sin(endLat) -
            Math.sin(startLat) * Math.cos(endLat) * Math.cos(dLng);

        return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
    };

    // Create a divIcon with rotatable inner element
    const createPlaneIcon = (bearing: number) => {
        return L.divIcon({
            className: 'plane-marker-container',
            html: `<div style="
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                transform: rotate(${bearing}deg);
                transform-origin: center;
            ">
                <span style="font-size: 28px;">✈️</span>
            </div>`,
            iconSize: [32, 32],
            iconAnchor: [16, 16],
        });
    };

    const animate = (time: number) => {
        if (!pathRef.current || pathRef.current.length < 2) return;
        if (!markerRef.current) {
            requestRef.current = requestAnimationFrame(animate);
            return;
        }

        if (!startTimeRef.current) {
            startTimeRef.current = time;
        }

        const path = pathRef.current;
        const elapsed = time - startTimeRef.current;
        const totalDuration = 20000;
        const progress = Math.min(elapsed / totalDuration, 1);

        const currentPointIndex = Math.floor(progress * (path.length - 1));
        const nextPointIndex = Math.min(currentPointIndex + 1, path.length - 1);
        const currentPoint = path[currentPointIndex];
        const nextPoint = path[nextPointIndex];

        if (currentPoint) {
            // Update marker position
            markerRef.current.setLatLng([currentPoint.lat, currentPoint.lng]);

            // Calculate and apply dynamic bearing
            if (nextPoint && currentPointIndex !== nextPointIndex) {
                const newBearing = calculateBearing(currentPoint, nextPoint);
                // Only update icon if bearing changed significantly (> 2 degrees)
                if (Math.abs(newBearing - bearingRef.current) > 2) {
                    bearingRef.current = newBearing;
                    markerRef.current.setIcon(createPlaneIcon(newBearing));
                }
            }
        }

        if (progress >= 1) {
            useAppStore.getState().removePlane(planeId);
            useAppStore.getState().decrementPendingVehicles();
            return;
        }

        requestRef.current = requestAnimationFrame(animate);
    };

    useEffect(() => {
        // Generate arc path
        pathRef.current = generateArcPath(sourceAirport, destAirport, 100);

        // Calculate initial bearing
        if (pathRef.current.length >= 2) {
            bearingRef.current = calculateBearing(pathRef.current[0], pathRef.current[1]);
        }

        // Start animation
        requestRef.current = requestAnimationFrame(animate);

        return () => {
            if (requestRef.current) {
                cancelAnimationFrame(requestRef.current);
            }
        };
    }, []);

    // Initial bearing for the icon
    const initialBearing = calculateBearing(sourceAirport, destAirport);

    return (
        <Marker
            position={[sourceAirport.lat, sourceAirport.lng]}
            icon={createPlaneIcon(initialBearing)}
            ref={markerRef}
        >
            <Popup>
                <div>
                    <strong>✈️ Flight in Progress</strong>
                    <p>{sourceAirport.name} → {destAirport.name}</p>
                    <p>Route ID: {routeId}</p>
                </div>
            </Popup>
        </Marker>
    );
};