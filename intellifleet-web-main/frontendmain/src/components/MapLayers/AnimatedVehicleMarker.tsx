import { useEffect, useRef } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import type { Vehicle, RoutePoint } from '../../types/api';
import { calculateBearing, interpolatePosition, calculateDistance } from '../../utils/mapUtils';
import './AnimatedVehiclePopup.css';
import { vehiclesApi } from '../../api/vehicles';
import { useAppStore } from '../../store/appStore';


interface AnimatedVehicleMarkerProps {
    vehicle: Vehicle;
    iconFactory: (type: string, isMoving: boolean) => L.Icon | null;
}

export const AnimatedVehicleMarker = ({ vehicle, iconFactory }: AnimatedVehicleMarkerProps) => {
    const markerRef = useRef<L.Marker | null>(null);
    const requestRef = useRef<number | undefined>(undefined);
    const startTimeRef = useRef<number | undefined>(undefined);
    const pathRef = useRef<RoutePoint[]>([]);
    const currentSegmentIndexRef = useRef(0);
    const bearingRef = useRef(0);
    const hasCompletedRef = useRef(false);
    const currentPositionRef = useRef<RoutePoint>(vehicle.current_position);

    // const lastSyncTimeRef = useRef<number>(0);
    // const SYNC_INTERVAL = 1000;

    // Initial position for the marker (only used once for initial render)
    //const [initialPosition] = useState<RoutePoint>(vehicle.current_position);

    // Speed in meters per second
    const SPEED_MPS = 90000; // Fast for demo purposes

    // Create rotated icon
    const icon = iconFactory(vehicle.type, true);

    // If icon is null (e.g., for planes which use PlanesLayer), don't render
    if (!icon) {
        return null;
    }

    const updateMarkerIcon = (newBearing: number) => {
        if (markerRef.current && bearingRef.current !== newBearing) {
            bearingRef.current = newBearing;
            const rotatedIcon = L.divIcon({
                className: 'vehicle-marker-container',
                html: `<img src="${icon.options.iconUrl}" style="transform: rotate(${newBearing}deg); width: 32px; height: 32px;" />`,
                iconSize: [32, 32],
                iconAnchor: [16, 16],
                popupAnchor: [0, -16]
            });
            markerRef.current.setIcon(rotatedIcon);
        }
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
        let segmentIndex = currentSegmentIndexRef.current;

        // If we reached the end
        // If we reached the end
        if (segmentIndex >= path.length - 1) {
            const finalPos = path[path.length - 1];
            markerRef.current.setLatLng([finalPos.lat, finalPos.lng]);
            // Track position for sync on unload (no re-render!)
            currentPositionRef.current = finalPos;

            console.log('Animation completed for vehicle:', vehicle.label);

            // Prevent duplicate API calls
            // if (!hasCompletedRef.current && vehicle.assigned_route) {
            //     hasCompletedRef.current = true;

            //     // Extract route_id from assigned_route
            //     const routeId = vehicle.assigned_route.route_id;
            //     const destination = vehicle.assigned_route.destination;

            //     // Call the completion API
            //     vehiclesApi.completeRoute({
            //         route_id: routeId,
            //         vehicle_id: vehicle.id,
            //         destination: destination
            //     })
            //         .then((response) => {
            //             console.log('Vehicle completed route:', response.message);
            //             // Update vehicle status in store
            //             markVehicleCompleted(vehicle.id, destination, finalPos);
            //         })
            //         .catch((error) => {
            //             console.error('Failed to complete vehicle route:', error);
            //             hasCompletedRef.current = false; // Allow retry on failure
            //         });
            // }

            // Prevent duplicate API calls
            if (!hasCompletedRef.current && vehicle.assigned_route) {
                hasCompletedRef.current = true;

                // Extract route_id from assigned_route
                const routeId = vehicle.assigned_route.route_id;
                const destination = vehicle.assigned_route.destination;

                // Check if this is a multimodal route segment
                const isMultimodalSegment = vehicle.assigned_route.route_data?.multimodal === true
                    || vehicle.assigned_route.destination?.includes('Airport');

                // if (isMultimodalSegment) {
                //     // For multimodal routes, just update position - don't call complete API
                //     console.log('Vehicle reached airport (multimodal segment):', vehicle.label);
                //     // Keep vehicle at airport, don't mark as completed
                //     useAppStore.getState().updateVehicle({
                //         ...vehicle,
                //         current_position: finalPos,
                //         current_location: destination
                //     });
                // }
                if (isMultimodalSegment) {
                    // Check if truck is already at destination (e.g., after reload)
                    // If so, don't trigger plane animation again
                    const path = pathRef.current;
                    const endOfPath = path[path.length - 1];
                    const alreadyAtDestination =
                        Math.abs(vehicle.current_position.lat - endOfPath.lat) < 0.0001 &&
                        Math.abs(vehicle.current_position.lng - endOfPath.lng) < 0.0001;

                    if (alreadyAtDestination) {
                        console.log('Truck already at airport, skipping plane animation');
                        return; // Don't trigger plane again
                    }
                    // For multimodal routes, just update position - don't call complete API
                    console.log('Vehicle reached airport (multimodal segment):', vehicle.label);

                    // Keep vehicle at airport, don't mark as completed
                    useAppStore.getState().updateVehicle({
                        ...vehicle,
                        current_position: finalPos,
                        current_location: destination
                    });

                    // Start plane animation if this is segment 1
                    const multimodalRoute = Object.values(useAppStore.getState().activeRoutes).find(
                        r => r.id === vehicle.assigned_route?.route_id && r.routeData?.multimodal
                    );

                    if (multimodalRoute?.routeData?.segments?.segment_2) {
                        const segment2 = multimodalRoute.routeData.segments.segment_2;

                        useAppStore.getState().addPlane({
                            id: `plane-${vehicle.assigned_route?.route_id}-${Date.now()}`,
                            routeId: vehicle.assigned_route?.route_id || 0,
                            sourceAirport: {
                                lat: segment2.source_airport.lat,
                                lng: segment2.source_airport.lng,
                                name: segment2.source_airport_name
                            },
                            destAirport: {
                                lat: segment2.destination_airport.lat,
                                lng: segment2.destination_airport.lng,
                                name: segment2.destination_airport_name
                            },
                            currentPosition: segment2.source_airport,
                            status: 'flying'
                        });
                    }
                } else {
                    // Regular route - call the completion API
                    vehiclesApi.completeRoute({
                        route_id: routeId,
                        vehicle_id: vehicle.id,
                        destination: destination
                    })
                        .then((response) => {
                            console.log('Vehicle completed route:', response.message);
                            // Update vehicle status in store
                            useAppStore.getState().markVehicleCompleted(vehicle.id, destination, finalPos);

                            // If this is part of a segment session, decrement pending vehicles
                            if (useAppStore.getState().segmentSession) {
                                useAppStore.getState().decrementPendingVehicles();
                            }
                        })
                        .catch((error) => {
                            console.error('Failed to complete vehicle route:', error);
                            hasCompletedRef.current = false; // Allow retry on failure
                        });
                }
            }



            return; // Stop animation
        }

        const startPoint = path[segmentIndex];
        const endPoint = path[segmentIndex + 1];
        const segmentDistance = calculateDistance(startPoint, endPoint);

        // Time needed for this segment
        const duration = (segmentDistance / SPEED_MPS) * 1000; // ms

        const elapsed = time - startTimeRef.current;

        if (elapsed < duration) {
            // Interpolate position
            const fraction = elapsed / duration;
            const newPos = interpolatePosition(startPoint, endPoint, fraction);

            // Direct Leaflet manipulation - NO React re-render!
            markerRef.current.setLatLng([newPos.lat, newPos.lng]);

            // if (time - lastSyncTimeRef.current > SYNC_INTERVAL) {
            //     lastSyncTimeRef.current = time;
            //     updateVehicle({
            //         ...vehicle,
            //         current_position: newPos
            //     });
            // }

            // Update bearing/rotation
            const newBearing = calculateBearing(startPoint, endPoint);
            updateMarkerIcon(newBearing);

            requestRef.current = requestAnimationFrame(animate);
        } else {
            // Move to next segment
            currentSegmentIndexRef.current++;
            startTimeRef.current = undefined; // Reset start time for next segment
            requestRef.current = requestAnimationFrame(animate);
        }
    };

    useEffect(() => {
        //dont animate when vehicle has reached 
        if (vehicle.status === 'completed') {
            hasCompletedRef.current = true;
            return;
        }
        // Initialize path from assigned route
        if (vehicle.assigned_route?.route_data?.optimal_routes?.[0]?.path) {
            pathRef.current = vehicle.assigned_route.route_data.optimal_routes[0].path;
            // currentSegmentIndexRef.current = 0;
            // startTimeRef.current = undefined;
            const currentPos = vehicle.current_position;
            const path = pathRef.current;
            let closestSegmentIdx = 0;
            let minDistance = Infinity;

            for (let i = 0; i < path.length - 1; i++) {
                const segmentStart = path[i];
                const dx = currentPos.lat - segmentStart.lat;
                const dy = currentPos.lng - segmentStart.lng;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < minDistance) {
                    minDistance = distance;
                    closestSegmentIdx = i;
                }

            }
            currentSegmentIndexRef.current = closestSegmentIdx;
            startTimeRef.current = undefined;


            if (pathRef.current.length > 0 && markerRef.current) {
                markerRef.current.setLatLng([currentPos.lat, currentPos.lng]);
                if (pathRef.current.length > 1) {
                    const initialBearing = calculateBearing(pathRef.current[closestSegmentIdx], pathRef.current[closestSegmentIdx + 1] || pathRef.current[closestSegmentIdx]);
                    updateMarkerIcon(initialBearing);
                }
            }

            // Start animation
            requestRef.current = requestAnimationFrame(animate);
        }

        return () => {
            if (requestRef.current) {
                cancelAnimationFrame(requestRef.current);
            }
        };
    }, [vehicle.assigned_route]); // Restart if route changes

    useEffect(() => {
        const handleBeforeUnload = () => {
            // Sync position to store only when leaving/reloading
            if (vehicle.status === 'assigned' && currentPositionRef.current) {
                // Direct store update using getState (avoid hook rules)
                useAppStore.getState().updateVehicle({
                    ...vehicle,
                    current_position: currentPositionRef.current
                });
            }
        };

        window.addEventListener('beforeunload', handleBeforeUnload);

        return () => {
            window.removeEventListener('beforeunload', handleBeforeUnload);
        };
    }, [vehicle]);

    // Initial icon with default bearing
    const initialIcon = L.divIcon({
        className: 'vehicle-marker-container',
        html: `<img src="${icon.options.iconUrl}" style="transform: rotate(0deg); width: 32px; height: 32px;" />`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        popupAnchor: [0, -16]
    });

    return (
        <Marker
            //position={[initialPosition.lat, initialPosition.lng]}
            position={[vehicle.current_position.lat, vehicle.current_position.lng]}
            icon={initialIcon}
            ref={markerRef}
        >
            <Popup>
                <div className="vehicle-popup">
                    <h3>{vehicle.type}</h3>
                    <p>ID: {vehicle.id}</p>
                    <p>Status: {vehicle.status}</p>
                    {/*<p>Moving...</p>*/}
                    {vehicle.assigned_route && (
                        <p>On Route: {vehicle.assigned_route.source} → {vehicle.assigned_route.destination}</p>
                    )}
                </div>
            </Popup>
        </Marker>
    );
};

