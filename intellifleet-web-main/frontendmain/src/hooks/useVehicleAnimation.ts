// import { useEffect, useRef } from 'react';
// import { useAppStore } from '../store/appStore';
// import { vehiclesApi } from '../api';

// const SPEED = 0.001; // Lat/Lng degrees per frame

// export const useVehicleAnimation = () => {
//     const { vehicles, updateVehicle } = useAppStore();
//     const requestRef = useRef<number>(0);

//     const animate = () => {
//         vehicles.forEach(vehicle => {
//             if (vehicle.status === 'assigned' && vehicle.assigned_route && vehicle.assigned_route.route_data?.optimal_routes?.[0]?.path) {
//                 const path = vehicle.assigned_route.route_data.optimal_routes[0].path;
//                 //console.log("path of assigned vehicle", path);
//                 if (path.length < 2) return;
//                 const sourceCoords = path[0];
//                 console.log("Source warehouse coordinates:, sourceCoords", sourceCoords);
//                 const destinationCoords = path[path.length - 1];
//                 console.log(`📍 Destination warehouse for vehicle ${vehicle.id}:`, destinationCoords);
//                 console.log(`   Latitude: ${destinationCoords.lat}`);
//                 console.log(`   Longitude: ${destinationCoords.lng}`);

//                 //console.log("path length of assigned vehicle", path.length);
//                 const currentPos = vehicle.current_position;
//                 //console.log("current position of assigned vehicle", currentPos);

//                 // Find the current segment the vehicle is on
//                 // Simple approach: Find the closest point in the path, then target the next one
//                 let closestIdx = 0;
//                 let minDist = Infinity;

//                 for (let i = 0; i < path.length; i++) {
//                     const p = path[i];
//                     const d = Math.sqrt(Math.pow(p.lat - currentPos.lat, 2) + Math.pow(p.lng - currentPos.lng, 2));
//                     if (d < minDist) {
//                         minDist = d;
//                         closestIdx = i;
//                     }
//                 }

//                 // Determine target point
//                 // If we are very close to the closest point, aim for the next one
//                 // If we are far, aim for the closest one (to get back on track)
//                 // let targetIdx = closestIdx;
//                 // if (minDist < 0.06) {
//                 //     targetIdx = closestIdx + 1;
//                 // }

//                 // If we reached the end
//                 if (targetIdx >= path.length) {
//                     // Call the complete vehicle route API
//                     const routeId = vehicle.assigned_route.route_data.route_id;
//                     const destination = vehicle.assigned_route.destination;

//                     console.log(`🎯 Vehicle ${vehicle.id} reached destination. Calling /vehicles_complete API...`);

//                     console.log(`Vehicle ID: ${vehicle.id}`);
//                     console.log(`Route ID: ${routeId}`);
//                     console.log(`Destination: ${destination}`);

//                     // Call API directly
//                     vehiclesApi.completeVehicleRoute(
//                         vehicle.id,
//                         routeId,
//                         destination
//                     ).then((response) => {
//                         console.log(`✅ Vehicle ${vehicle.id} completed route ${routeId} to ${destination}`, response);
//                     }).catch(error => {
//                         console.error('❌ Failed to complete vehicle route:', error);
//                     });

//                     // Update vehicle state: mark as available, clear assignment, but keep route on map
//                     updateVehicle({
//                         ...vehicle,
//                         current_position: path[path.length - 1],
//                         status: 'available',
//                         is_available: true,
//                         current_location: destination,
//                         assigned_route: undefined // Clear vehicle's route assignment (vehicle is free)
//                     });
//                     return;
//                 }

//                 const target = path[targetIdx];
//                 console.log("target path to stop vehicle", target);
//                 const dx = target.lat - currentPos.lat;
//                 const dy = target.lng - currentPos.lng;
//                 const distance = Math.sqrt(dx * dx + dy * dy);

//                 if (distance > 0) {
//                     // Move towards target
//                     // Adjust speed based on distance to avoid overshooting
//                     const moveDist = Math.min(SPEED, distance);
//                     const ratio = moveDist / distance;

//                     const newLat = currentPos.lat + dx * ratio;
//                     const newLng = currentPos.lng + dy * ratio;

//                     updateVehicle({
//                         ...vehicle,
//                         current_position: { lat: newLat, lng: newLng }
//                     });
//                 }
//             }
//         });

//         requestRef.current = requestAnimationFrame(animate);
//     };

//     useEffect(() => {
//         requestRef.current = requestAnimationFrame(animate);
//         return () => cancelAnimationFrame(requestRef.current);
//     }, [vehicles]); // Removed updateVehicle from dependency to avoid loop, though zustand actions are stable
// };

// 

// import { useEffect, useRef } from 'react';
// import { useAppStore } from '../store/appStore';
// import { vehiclesApi } from '../api';

// const SPEED = 0.001; // Lat/Lng degrees per frame
// const WAYPOINT_REACHED_THRESHOLD = 0.0001; // Very small threshold to consider waypoint reached

// export const useVehicleAnimation = () => {
//     const { vehicles, updateVehicle } = useAppStore();
//     const requestRef = useRef<number>(0);
//     const completedRoutesRef = useRef<Set<string>>(new Set()); // Track completed routes to prevent duplicate API calls

//     const animate = () => {
//         vehicles.forEach(vehicle => {
//             if (vehicle.status === 'assigned' && vehicle.assigned_route && vehicle.assigned_route.route_data?.optimal_routes?.[0]?.path) {
//                 const path = vehicle.assigned_route.route_data.optimal_routes[0].path;

//                 if (path.length < 2) {
//                     console.log(`⚠️ Vehicle ${vehicle.id}: Path too short (${path.length} points)`);
//                     return;
//                 }

//                 const currentPos = vehicle.current_position;
//                 const routeKey = `${vehicle.id}-${vehicle.assigned_route.route_data.route_id}`;

//                 // Find the closest point on path
//                 let closestIdx = 0;
//                 let minDist = Infinity;

//                 for (let i = 0; i < path.length; i++) {
//                     const p = path[i];
//                     const d = Math.sqrt(Math.pow(p.lat - currentPos.lat, 2) + Math.pow(p.lng - currentPos.lng, 2));
//                     if (d < minDist) {
//                         minDist = d;
//                         closestIdx = i;
//                     }
//                 }

//                 const isLastWaypoint = closestIdx === path.length - 1;

//                 console.log(`🚗 Vehicle ${vehicle.id}:`);
//                 console.log(`   Current waypoint: ${closestIdx + 1}/${path.length}`);
//                 console.log(`   Distance to waypoint: ${minDist.toFixed(6)}`);
//                 console.log(`   Is at last waypoint: ${isLastWaypoint}`);

//                 // Check if vehicle has reached the last waypoint (destination)
//                 if (isLastWaypoint && minDist < WAYPOINT_REACHED_THRESHOLD) {
//                     // Prevent duplicate API calls for the same route
//                     if (completedRoutesRef.current.has(routeKey)) {
//                         console.log(`⏭️ Vehicle ${vehicle.id}: Route already completed, skipping`);
//                         return;
//                     }

//                     const routeId = vehicle.assigned_route.route_data.route_id;
//                     const destination = vehicle.assigned_route.destination;

//                     console.log(`🎯 Vehicle ${vehicle.id} REACHED FINAL DESTINATION!`);
//                     console.log(`   ✓ At last waypoint (${closestIdx + 1}/${path.length})`);
//                     console.log(`   ✓ Distance: ${minDist.toFixed(6)} < threshold: ${WAYPOINT_REACHED_THRESHOLD}`);
//                     console.log(`   Vehicle ID: ${vehicle.id}`);
//                     console.log(`   Route ID: ${routeId}`);
//                     console.log(`   Destination: ${destination}`);
//                     console.log(`   📞 Calling /vehicles_complete API...`);

//                     // Mark route as completed before API call to prevent duplicates
//                     completedRoutesRef.current.add(routeKey);

//                     // Call API to complete the route
//                     vehiclesApi.completeVehicleRoute(
//                         vehicle.id,
//                         routeId,
//                         destination
//                     ).then((response) => {
//                         console.log(`✅ SUCCESS: Vehicle ${vehicle.id} completed route ${routeId}`, response);
//                     }).catch(error => {
//                         console.error(`❌ ERROR: Vehicle ${vehicle.id} failed to complete route:`, error);
//                         // Remove from completed set on failure so it can retry
//                         completedRoutesRef.current.delete(routeKey);
//                     });

//                     // Update vehicle state: mark as available, snap to final position
//                     console.log(`📍 Updating vehicle ${vehicle.id} state to AVAILABLE at destination`);
//                     updateVehicle({
//                         ...vehicle,
//                         current_position: path[path.length - 1], // Snap to exact final position
//                         status: 'available',
//                         is_available: true,
//                         current_location: destination,
//                         assigned_route: undefined // Clear vehicle's route assignment
//                     });
//                     return;
//                 }

//                 // Determine target waypoint
//                 let targetIdx = closestIdx;

//                 // If very close to current waypoint, move to next one
//                 if (minDist < WAYPOINT_REACHED_THRESHOLD && closestIdx < path.length - 1) {
//                     targetIdx = closestIdx + 1;
//                     console.log(`   ➡️ Reached waypoint ${closestIdx + 1}, moving to waypoint ${targetIdx + 1}`);
//                 }

//                 const target = path[targetIdx];
//                 const dx = target.lat - currentPos.lat;
//                 const dy = target.lng - currentPos.lng;
//                 const distance = Math.sqrt(dx * dx + dy * dy);

//                 if (distance > 0) {
//                     // Move towards target waypoint
//                     const moveDist = Math.min(SPEED, distance);
//                     const ratio = moveDist / distance;

//                     const newLat = currentPos.lat + dx * ratio;
//                     const newLng = currentPos.lng + dy * ratio;

//                     console.log(`   🚀 Moving to waypoint ${targetIdx + 1}: distance ${distance.toFixed(6)}`);

//                     updateVehicle({
//                         ...vehicle,
//                         current_position: { lat: newLat, lng: newLng }
//                     });
//                 }
//             }
//         });

//         requestRef.current = requestAnimationFrame(animate);
//     };

//     useEffect(() => {
//         console.log('🎬 Starting vehicle animation loop');
//         requestRef.current = requestAnimationFrame(animate);
//         return () => {
//             console.log('🛑 Stopping vehicle animation loop');
//             cancelAnimationFrame(requestRef.current);
//         };
//     }, [vehicles]);
// };

// import { useEffect, useRef } from 'react';
// import { useAppStore } from '../store/appStore';
// import { vehiclesApi } from '../api';

// const SPEED = 0.001; // Lat/Lng degrees per frame
// const DESTINATION_THRESHOLD = 0.0001; // Threshold to consider vehicle has reached destination

// export const useVehicleAnimation = () => {
//     const { vehicles, updateVehicle } = useAppStore();
//     const requestRef = useRef<number>(0);
//     const completedRoutesRef = useRef<Set<string>>(new Set()); // Prevent duplicate API calls

//     const animate = () => {
//         vehicles.forEach(vehicle => {
//             if (vehicle.status === 'assigned' && vehicle.assigned_route && vehicle.assigned_route.route_data?.optimal_routes?.[0]?.path) {
//                 const path = vehicle.assigned_route.route_data.optimal_routes[0].path;

//                 if (path.length < 2) return;

//                 const sourceCoords = path[0];
//                 console.log("Source warehouse coordinates:", sourceCoords);

//                 const destinationCoords = path[path.length - 1];
//                 console.log(`📍 Destination warehouse for vehicle ${vehicle.id}:`, destinationCoords);
//                 console.log(`   Latitude: ${destinationCoords.lat}`);
//                 console.log(`   Longitude: ${destinationCoords.lng}`);

//                 const currentPos = vehicle.current_position;
//                 console.log(`🚗 Current position of vehicle ${vehicle.id}:`, currentPos);

//                 // Calculate distance between current position and destination
//                 const distanceToDestination = Math.sqrt(
//                     Math.pow(destinationCoords.lat - currentPos.lat, 2) +
//                     Math.pow(destinationCoords.lng - currentPos.lng, 2)
//                 );

//                 console.log(`📏 Distance to destination: ${distanceToDestination.toFixed(8)}`);

//                 // Check if vehicle has reached the destination
//                 if (distanceToDestination < DESTINATION_THRESHOLD) {
//                     const routeKey = `${vehicle.id}-${vehicle.assigned_route.route_data.route_id}`;

//                     // Prevent duplicate API calls
//                     if (completedRoutesRef.current.has(routeKey)) {
//                         console.log(`⏭️ Vehicle ${vehicle.id}: Already completed this route, skipping`);
//                         return;
//                     }

//                     const routeId = vehicle.assigned_route.route_data.route_id;
//                     const destination = vehicle.assigned_route.destination;

//                     console.log(`🎯 Vehicle ${vehicle.id} REACHED DESTINATION!`);
//                     console.log(`   Current position: lat=${currentPos.lat}, lng=${currentPos.lng}`);
//                     console.log(`   Destination coords: lat=${destinationCoords.lat}, lng=${destinationCoords.lng}`);
//                     console.log(`   Distance: ${distanceToDestination.toFixed(8)} < threshold: ${DESTINATION_THRESHOLD}`);
//                     console.log(`   Vehicle ID: ${vehicle.id}`);
//                     console.log(`   Route ID: ${routeId}`);
//                     console.log(`   Destination: ${destination}`);
//                     console.log(`   📞 Calling /vehicles_complete API...`);

//                     // Mark as completed to prevent duplicate calls
//                     completedRoutesRef.current.add(routeKey);

//                     // Call API to complete vehicle route
//                     vehiclesApi.completeVehicleRoute(
//                         vehicle.id,
//                         routeId,
//                         destination
//                     ).then((response) => {
//                         console.log(`✅ Vehicle ${vehicle.id} completed route ${routeId} to ${destination}`, response);
//                     }).catch(error => {
//                         console.error('❌ Failed to complete vehicle route:', error);
//                         // Remove from completed set on failure so it can retry
//                         completedRoutesRef.current.delete(routeKey);
//                     });

//                     // Update vehicle state: mark as available, clear assignment
//                     updateVehicle({
//                         ...vehicle,
//                         current_position: destinationCoords, // Snap to exact destination coordinates
//                         status: 'available',
//                         is_available: true,
//                         current_location: destination,
//                         assigned_route: undefined // Clear vehicle's route assignment (vehicle is free)
//                     });
//                     return;
//                 }

//                 // Continue animation - find closest point on path
//                 let closestIdx = 0;
//                 let minDist = Infinity;

//                 for (let i = 0; i < path.length; i++) {
//                     const p = path[i];
//                     const d = Math.sqrt(Math.pow(p.lat - currentPos.lat, 2) + Math.pow(p.lng - currentPos.lng, 2));
//                     if (d < minDist) {
//                         minDist = d;
//                         closestIdx = i;
//                     }
//                 }

//                 // Determine target point
//                 let targetIdx = closestIdx;
//                 if (minDist < 0.0001) {
//                     targetIdx = closestIdx + 1;
//                 }

//                 // Safety check
//                 if (targetIdx >= path.length) {
//                     targetIdx = path.length - 1;
//                 }

//                 const target = path[targetIdx];
//                 console.log(`   Target waypoint ${targetIdx + 1}/${path.length}:`, target);

//                 const dx = target.lat - currentPos.lat;
//                 const dy = target.lng - currentPos.lng;
//                 const distance = Math.sqrt(dx * dx + dy * dy);

//                 if (distance > 0) {
//                     // Move towards target
//                     const moveDist = Math.min(SPEED, distance);
//                     const ratio = moveDist / distance;

//                     const newLat = currentPos.lat + dx * ratio;
//                     const newLng = currentPos.lng + dy * ratio;

//                     updateVehicle({
//                         ...vehicle,
//                         current_position: { lat: newLat, lng: newLng }
//                     });
//                 }
//             }
//         });

//         requestRef.current = requestAnimationFrame(animate);
//     };

//     useEffect(() => {
//         console.log('🎬 Starting vehicle animation loop');
//         requestRef.current = requestAnimationFrame(animate);
//         return () => {
//             console.log('🛑 Stopping vehicle animation loop');
//             cancelAnimationFrame(requestRef.current);
//         };
//     }, [vehicles]);
// };

// import { useEffect, useRef } from 'react';
// import { useAppStore } from '../store/appStore';
// import { vehiclesApi } from '../api';

// // const SPEED = 0.001; // Lat/Lng degrees per frame
// // const DESTINATION_THRESHOLD = 0.0005;
// //  // Distance threshold to consider vehicle reached destination
// const SPEED = 0.001; // Lat/Lng degrees per frame (~100m at equator)
// const DESTINATION_THRESHOLD = 0.002; // Increased + made reliable with snapping

// export const useVehicleAnimation = () => {
//     const { vehicles, updateVehicle } = useAppStore();
//     const requestRef = useRef<number>(0);
//     const completedRoutesRef = useRef<Set<string>>(new Set()); // Prevent duplicate API calls

//     const animate = () => {
//         vehicles.forEach(vehicle => {
//             if (vehicle.status === 'assigned' && vehicle.assigned_route && vehicle.assigned_route.route_data?.optimal_routes?.[0]?.path) {
//                 const path = vehicle.assigned_route.route_data.optimal_routes[0].path;

//                 if (path.length < 2) return;

//                 const currentPos = vehicle.current_position;
//                 console.log(`Current position of vehicle ${vehicle.id}:`, currentPos);

//                 const destinationCoords = path[path.length - 1]; // Last point = destination
//                 console.log(`Destination of vehicle ${vehicle.id}:`, destinationCoords);

//                 // Calculate distance between current position and destination
//                 const distanceToDestination = Math.sqrt(
//                     Math.pow(destinationCoords.lat - currentPos.lat, 2) +
//                     Math.pow(destinationCoords.lng - currentPos.lng, 2)
//                 );

//                 // Check if vehicle reached destination
//                 if (distanceToDestination < DESTINATION_THRESHOLD) {
//                     const routeKey = `${vehicle.id}-${vehicle.assigned_route.route_data.route_id}`;

//                     // Prevent duplicate API calls
//                     if (completedRoutesRef.current.has(routeKey)) {
//                         return;
//                     }

//                     const routeId = vehicle.assigned_route.route_data.route_id;
//                     const destination = vehicle.assigned_route.destination;

//                     console.log(`🎯 Vehicle ${vehicle.id} reached destination!`);
//                     console.log(`📞 Calling /vehicles_complete API...`);

//                     // Mark as completed
//                     completedRoutesRef.current.add(routeKey);

//                     // Call API
//                     vehiclesApi.completeVehicleRoute(
//                         vehicle.id,
//                         routeId,
//                         destination
//                     ).then((response) => {
//                         console.log(`✅ Vehicle ${vehicle.id} completed route ${routeId}`, response);
//                     }).catch(error => {
//                         console.error('❌ Failed to complete vehicle route:', error);
//                         completedRoutesRef.current.delete(routeKey); // Allow retry on failure
//                     });

//                     // Update vehicle state
//                     updateVehicle({
//                         ...vehicle,
//                         current_position: destinationCoords,
//                         status: 'available',
//                         is_available: true,
//                         current_location: destination,
//                         assigned_route: undefined
//                     });
//                     return;
//                 }

//                 // Continue animation - find closest point and move toward next
//                 let closestIdx = 0;
//                 let minDist = Infinity;

//                 for (let i = 0; i < path.length; i++) {
//                     const p = path[i];
//                     const d = Math.sqrt(Math.pow(p.lat - currentPos.lat, 2) + Math.pow(p.lng - currentPos.lng, 2));
//                     if (d < minDist) {
//                         minDist = d;
//                         closestIdx = i;
//                     }
//                 }

//                 // Target next point if close to current
//                 let targetIdx = closestIdx;
//                 if (minDist < SPEED * 2 && closestIdx < path.length - 1) {
//                     targetIdx = closestIdx + 1;
//                 }

//                 const target = path[targetIdx];
//                 const dx = target.lat - currentPos.lat;
//                 const dy = target.lng - currentPos.lng;
//                 const distance = Math.sqrt(dx * dx + dy * dy);

//                 if (distance > 0) {
//                     const moveDist = Math.min(SPEED, distance);
//                     const ratio = moveDist / distance;

//                     updateVehicle({
//                         ...vehicle,
//                         current_position: {
//                             lat: currentPos.lat + dx * ratio,
//                             lng: currentPos.lng + dy * ratio
//                         }
//                     });
//                 }
//             }
//         });

//         requestRef.current = requestAnimationFrame(animate);
//     };

//     useEffect(() => {
//         requestRef.current = requestAnimationFrame(animate);
//         return () => cancelAnimationFrame(requestRef.current);
//     }, [vehicles]);
// };


// Simplified Vehicle Animation - Vehicles stop at destination
import { useEffect, useRef } from 'react';
import { useAppStore } from '../store/appStore';

const SPEED = 0.0008; // Lat/Lng degrees per frame
const DESTINATION_THRESHOLD = 0.0005; // Close enough to destination

export const useVehicleAnimation = () => {
    const { vehicles, updateVehicle } = useAppStore();
    const requestRef = useRef<number>(0);
    const vehicleProgressRef = useRef<Map<number, number>>(new Map()); // Track waypoint index per vehicle

    const animate = () => {
        vehicles.forEach(vehicle => {
            // Only animate assigned vehicles with valid routes
            if (
                vehicle.status !== 'assigned' ||
                !vehicle.assigned_route ||
                !vehicle.assigned_route.route_data?.optimal_routes?.[0]?.path
            ) {
                return;
            }

            const path = vehicle.assigned_route.route_data.optimal_routes[0].path;
            if (path.length < 2) return;

            const currentPos = vehicle.current_position;
            const destinationCoords = path[path.length - 1];

            // Get or initialize the current waypoint index for this vehicle
            let currentWaypointIdx = vehicleProgressRef.current.get(vehicle.id) || 0;

            // Get the current target waypoint
            const targetWaypoint = path[currentWaypointIdx];

            // Calculate distance to current target waypoint
            const dx = targetWaypoint.lat - currentPos.lat;
            const dy = targetWaypoint.lng - currentPos.lng;
            const distanceToWaypoint = Math.sqrt(dx * dx + dy * dy);

            // Check if we've reached the current waypoint
            if (distanceToWaypoint < DESTINATION_THRESHOLD) {
                // Move to next waypoint
                currentWaypointIdx++;
                vehicleProgressRef.current.set(vehicle.id, currentWaypointIdx);

                // Check if we've reached the final destination
                if (currentWaypointIdx >= path.length) {
                    console.log(`🎯 Vehicle ${vehicle.id} reached destination!`);

                    // Snap to exact destination and keep vehicle visible at destination
                    // DO NOT remove assigned_route - this keeps vehicle visible on map
                    updateVehicle({
                        ...vehicle,
                        current_position: {
                            lat: destinationCoords.lat,
                            lng: destinationCoords.lng
                        }
                        // Vehicle stays 'assigned' and visible at destination
                    });

                    // Clean up progress tracking
                    vehicleProgressRef.current.delete(vehicle.id);
                    return;
                }
            }

            // Move toward current target waypoint
            if (distanceToWaypoint > DESTINATION_THRESHOLD) {
                const moveDist = Math.min(SPEED, distanceToWaypoint);
                const ratio = moveDist / distanceToWaypoint;

                const newLat = currentPos.lat + dx * ratio;
                const newLng = currentPos.lng + dy * ratio;

                updateVehicle({
                    ...vehicle,
                    current_position: {
                        lat: newLat,
                        lng: newLng
                    }
                });
            }
        });

        // Continue animation loop
        requestRef.current = requestAnimationFrame(animate);
    };

    useEffect(() => {
        requestRef.current = requestAnimationFrame(animate);

        return () => {
            if (requestRef.current) {
                cancelAnimationFrame(requestRef.current);
            }
        };
    }, [vehicles]);

    return null;
};