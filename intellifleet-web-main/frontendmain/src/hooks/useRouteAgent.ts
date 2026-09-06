import { useState, useRef } from 'react';
import { chatApi } from '../api/chat';
import { useAppStore } from '../store/appStore';
import type { ChatAction } from '../types/api';
import { formatDuration } from '../utils/formatDuration';
import { decodePolyline } from '../utils/decodePolyline';
import { vehiclesApi } from '../api/vehicles';

// Helper function to format route response with detailed information
const formatRouteResponse = (data: any): string => {
    if (!data || !data.optimal_routes || data.optimal_routes.length === 0) {
        return "Route planned successfully.";
    }

    const optimal = data.optimal_routes[0];
    const routeId = data.route_id || 'N/A';
    const source = data.source || '';
    const destination = data.destination || '';
    const distance = optimal.distance || 'N/A';

    const duration = optimal.duration ? formatDuration(optimal.duration) : 'N/A';

    // Determine route type and stops
    const intermediateLocations = data.intermediate_locations || [];
    const hasIntermediates = intermediateLocations.length > 0;
    const routeType = hasIntermediates ? 'Multi-stop route' : 'Optimal';
    const totalStops = 2 + intermediateLocations.length;
    const intermediateCount = intermediateLocations.length;

    // Build route path string
    let routePath = source;
    if (hasIntermediates) {
        routePath += ` → ${intermediateLocations.join(' → ')}`;
    }
    routePath += ` → ${destination}`;

    // Format the detailed message
    const detailedMessage =
        `📍 Route ${routeId} Displayed ●\n\n` +
        `Route: ${routePath}\n` +
        `Distance: ${distance}\n` +
        `Estimated Time: ${duration}\n` +
        `Route Type: ${routeType}\n` +
        `Total Stops: ${totalStops} (${intermediateCount} intermediate)\n` +
        `Route ID: ${routeId}`;

    // Confirmation message
    const confirmationMessage =
        `I've planned route #${routeId} from ${source} to ${destination}. ` +
        `You can now assign vehicles to this route.`;

    // Combine both messages
    return `${detailedMessage}\n\n${confirmationMessage}`;
};


export const useRouteAgent = () => {
    const [isProcessing, setIsProcessing] = useState(false);
    const sessionIdRef = useRef<string | undefined>(undefined);
    const startNewSession = () => { sessionIdRef.current = crypto.randomUUID(); };

    const {
        vehicles,
        activeRoutes,
        addActiveRoute,
        removeActiveRoute,
        markRouteAsInactive,
        addChatMessage,
        updateVehicle,
        clearActiveRoutes,
        clearChatHistory,
        setMapViewMode,
        updateWarehouse,
    } = useAppStore();

    const processMessage = async (message: string) => {
        if (!message.trim()) return;

        setIsProcessing(true);
        // User message is added by UI component usually, but we ensure state consistency if needed

        try {
            // Call /agent endpoint
            if (!sessionIdRef.current) startNewSession();
            const response = await chatApi.sendMessage(message, sessionIdRef.current);

            // Update session ID
            if (response.session_id) {
                sessionIdRef.current = response.session_id;
            }

            // Add Assistant Response (old code — commented out)
            // if (response.response) {
            //     if (response.response === "Chat conversation history cleared.") {
            //         // Fallback: if no action but response is "Chat conversation history cleared.", clear it manually.
            //         addChatMessage('assistant', response.response);
            //     } else if (response.response === "Error planning route.") {
            //         //console.log(response.response);
            //         addChatMessage('assistant', "No route found for the given source and destination.");
            //     } else {
            //         // Check if this is a route planning success response
            //         const isPlanRouteAction = response.actions?.some(action =>
            //             action.type === 'plan_route' || action.type === 'display_route'
            //         );

            //         if (isPlanRouteAction && response.data) {
            //             // Format detailed route information
            //             const formattedMessage = formatRouteResponse(response.data);
            //             addChatMessage('assistant', formattedMessage);
            //         } else {
            //             addChatMessage('assistant', response.response);
            //         }
            //     }
            // }

            // Handle Actions
            if (response.actions && response.actions.length > 0) {
                for (const action of response.actions) {
                    await handleAction(action);
                }
            }

            // Add Assistant Response
            if (response.response) {
                // Check if this is a fetch_routes action with an "answer" key
                const fetchRoutesAction = response.actions?.find(
                    (action: any) => action.type === 'fetch_routes'
                );
                if (fetchRoutesAction?.data?.answer) {
                    // Use the "answer" text from the action data instead of response.response
                    addChatMessage('assistant', fetchRoutesAction.data.answer);
                } else if (response.response === "Chat conversation history cleared.") {
                    addChatMessage('assistant', response.response);
                } else if (response.response === "Error planning route.") {
                    addChatMessage('assistant', "No route found for the given source and destination.");
                } else {
                    const isPlanRouteAction = response.actions?.some(action =>
                        action.type === 'plan_route' || action.type === 'display_route'
                    );

                    if (isPlanRouteAction && response.data) {
                        const formattedMessage = formatRouteResponse(response.data);
                        addChatMessage('assistant', formattedMessage);
                    } else {
                        addChatMessage('assistant', response.response);
                    }
                }
            }


        } catch (error: any) {
            //console.error('Agent processing error:', error);
            addChatMessage('assistant', `${error.message || 'Unknown error'}. Please try again.`);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleAction = async (action: ChatAction) => {
        //console.log('Executing Action:', action);
        switch (action.type) {
            case "plan_route":
            case 'display_route':
                handleDisplayRouteAction(action.data);
                break;
            case 'assign_vehicles':
                handleAssignVehicleAction(action.data);
                break;
            case 'list_vehicles':
                // The text response usually covers this, but we could trigger a UI side panel here
                break;
            case 'clear_chat':
                handleClearChatAction();
                break;
            case 'clear_map':
                handleClearMap();
                break;
            case 'satellite_view':
                handleSatelliteView();
                break;
            case 'street_view':
                handleStreetView();
                break;
            case "remove_route":
            case "remove_multimodal_route":
                handleRemoveRouteAction(action.data);
                break;
            case "alternative_route":
                handleAlternativeRouteAction(action.data);
                break;
            case "reset_vehicle":
                handleResetVehicleAction(action.data);
                break;
            case "multimodal_route":
                handleMultimodalRouteAction(action.data);
                break;
            case "assign_vehicle_multimodal":
                await handleMultimodalAssignVehicle(action);
                break;
            case "connect_hub":
                handleConnectHubAction(action.data);
                break;
            case "warehouse_status_update":
                handleWarehouseStatusUpdate(action.data);
                break;
            case "reset_all_vehicles":
                handleResetAllVehicles();
                break;
            case "fetch_routes":
                handleFetchRoutes(action.data);
                break;
            case "assign_plane":
                handleAssignPlaneAction(action);
                break;
            case "vehicle_status_update":
                handleVehicleStatusUpdate(action.data);
                break;
            case "route_status_update":
                handleRouteStatusUpdate(action.data);
                break;
            case "air_intermediate_route":
                handleAirIntermediateRouteAction(action.data);
                break;
            case "partial_assignment_start":
                handlePartialAssignmentStart(action.data);
                break;
            case "animate_segment":
                await handleAnimateSegment(action.data);
                break;
            case "manage_disruption_tool":
                handleManageDisruption(action.data);
                break;
            case "unified_supply_chain_plan":
            case "supply_chain_planning_operation":
                handlePlanningResult(action.data);
                break;
            default:
                console.warn('Unknown action type:', action.type);
        }
    };

    // --- Action Handlers ---

    const handlePartialAssignmentStart = (data: any) => {
        const { setSegmentSession } = useAppStore.getState();
        setSegmentSession({
            sessionId: data.session_id,
            partial: data.partial,
            segmentIndex: 0,
            totalSegments: data.total_segments || 1
        });
    };

    const handleAnimateSegment = async (data: any) => {
        await processSegment(data.segment, data.session_id, data.partial);
    };

    const processSegment = async (segment: any, sessionId: string, isPartial: boolean) => {
        // IMPORTANT: Always read from getState() to avoid stale closures
        // when processSegment is called from onSegmentComplete callback
        const { setOnSegmentComplete, setPendingVehiclesCount, vehicles: currentVehicles, activeRoutes: currentActiveRoutes, updateVehicle: storeUpdateVehicle } = useAppStore.getState();

        // 1. Process vehicles
        if (segment.route_type === 'air' || segment.route_type === 'flight') {
            const { addPlane } = useAppStore.getState();
            segment.assigned_vehicles?.forEach((planeData: any) => {
                const planeVehicle = currentVehicles.find(v => v.id === planeData.vehicle_id);
                if (planeVehicle) {
                    const sourceAirport = segment.airport_info?.source_airport;
                    const destAirport = segment.airport_info?.destination_airport;

                    storeUpdateVehicle({
                        ...planeVehicle,
                        status: 'assigned',
                        is_available: false,
                        type: 'plane' as any,
                        current_location: segment.from,
                        current_position: { lat: sourceAirport.latitude, lng: sourceAirport.longitude },
                        departure_time: planeData.departure_time,
                        arrival_time: planeData.arrival_time,
                        capacity: planeData.capacity_kg,
                        vehicle_details: planeData.vehicle_details,
                        assigned_route: {
                            route_id: segment.route_id,
                            route_data: { route_id: segment.route_id, optimal_routes: [] },
                            waypoints: [segment.from, segment.to],
                            source: segment.from,
                            destination: segment.to,
                            intermediate_locations: [],
                            assigned_at: new Date().toISOString(),
                            vehicle_type: 'plane',
                            vehicle_details: planeData.vehicle_details,
                            route_cost: planeData.segment_cost?.toString() || null,
                            distance: segment.distance_km,
                            departure_time: planeData.departure_time,
                            arrival_time: planeData.arrival_time,
                        }
                    });

                    addPlane({
                        id: `plane-${segment.route_id}-${planeData.vehicle_id}-${Date.now()}`,
                        routeId: segment.route_id,
                        sourceAirport: {
                            lat: sourceAirport.latitude,
                            lng: sourceAirport.longitude,
                            name: sourceAirport.name
                        },
                        destAirport: {
                            lat: destAirport.latitude,
                            lng: destAirport.longitude,
                            name: destAirport.name
                        },
                        currentPosition: {
                            lat: sourceAirport.latitude,
                            lng: sourceAirport.longitude
                        },
                        status: 'flying'
                    });
                }
            });

            // Set pending to number of assigned planes (typically 1, but handles multiple)
            const planeCount = segment.assigned_vehicles?.length || 1;
            setPendingVehiclesCount(planeCount);
        } else {
            // Road segment
            const route = currentActiveRoutes[segment.route_id];
            if (!route) {
                console.error(`Route ${segment.route_id} not found for segment`);
                return;
            }

            const routeDataForVehicle = JSON.parse(JSON.stringify(route.routeData));
            if (routeDataForVehicle?.optimal_routes?.[0]?.path && typeof routeDataForVehicle.optimal_routes[0].path === 'string') {
                routeDataForVehicle.optimal_routes[0].path = decodePolyline(routeDataForVehicle.optimal_routes[0].path);
            }

            const startPosition = route.routeData?.source_coords
                || routeDataForVehicle?.optimal_routes?.[0]?.path?.[0]
                || { lat: 0, lng: 0 };

            const STAGGER_DELAY_MS = 3000;
            const assignedCount = segment.assigned_vehicles?.length || 0;
            setPendingVehiclesCount(assignedCount);

            segment.assigned_vehicles?.forEach((assignedData: any, index: number) => {
                const vehicle = currentVehicles.find(v => v.id === assignedData.vehicle_id);
                if (!vehicle) return;

                const assignVehicle = () => {
                    storeUpdateVehicle({
                        ...vehicle,
                        status: 'assigned',
                        is_available: false,
                        current_location: segment.from,
                        current_position: startPosition,
                        departure_time: assignedData.departure_time,
                        arrival_time: assignedData.arrival_time,
                        capacity: assignedData.capacity_kg || vehicle.capacity,
                        vehicle_details: assignedData.vehicle_details || vehicle.vehicle_details,
                        assigned_route: {
                            route_id: segment.route_id,
                            route_data: routeDataForVehicle,
                            waypoints: route.waypoints,
                            source: segment.from,
                            destination: segment.to,
                            intermediate_locations: route.intermediates,
                            assigned_at: new Date().toISOString(),
                            vehicle_type: assignedData.vehicle_type || vehicle.type,
                            vehicle_details: assignedData.vehicle_details || {},
                            route_cost: assignedData.segment_cost?.toString() || null,
                            distance: segment.distance_km,
                            departure_time: assignedData.departure_time,
                            arrival_time: assignedData.arrival_time,
                        }
                    });
                };

                if (index === 0) {
                    assignVehicle();
                } else {
                    setTimeout(assignVehicle, index * STAGGER_DELAY_MS);
                }
            });

            // Zoom to the active route
            const { setLastAssignedRouteId } = useAppStore.getState();
            setLastAssignedRouteId(segment.route_id);
        }

        // 2. Setup next segment fetch on completion
        if (isPartial === false) {
            setOnSegmentComplete(async () => {
                const { setOnSegmentComplete: clearCallback } = useAppStore.getState();
                clearCallback(null); // Clear to prevent double triggering
                try {
                    console.log(`Fetching next segment for session ${sessionId}...`);
                    const response = await vehiclesApi.fetchNextSegment(sessionId);
                    if (response.success && response.data?.segment) {
                        const nextIsPartial = response.data.partial;
                        await processSegment(response.data.segment, sessionId, nextIsPartial);
                    }
                } catch (error) {
                    console.error('Failed to fetch next segment', error);
                }
            });
        } else {
            setOnSegmentComplete(() => {
                console.log('Final segment completed.');
                const { setSegmentSession, setOnSegmentComplete: clearCallback } = useAppStore.getState();
                clearCallback(null);
                setSegmentSession(null);
            });
        }
    };

    const handleFetchRoutes = (data: any) => {
        console.log("Fetch routes action received", data);

        if (data?.route_id) {
            const routeId = data.route_id;
            // Zoom to the route
            const { setLastCreatedRouteId, setHighlightedRouteIds } = useAppStore.getState();
            setLastCreatedRouteId(routeId);
            // Highlight with yellow
            setHighlightedRouteIds([routeId]);
        }
    };

    const handleManageDisruption = (data: any) => {
        console.log("Manage disruption action received", data);

        const innerData = data?.data || data;
        const routeIds: number[] = innerData?.route_ids || [];

        if (routeIds.length > 0) {
            const { setHighlightedRouteIds, setLastCreatedRouteId } = useAppStore.getState();
            // Highlight all disrupted routes with yellow
            setHighlightedRouteIds(routeIds);
            // Zoom to the first route (triggers the existing zoom useEffect)
            setLastCreatedRouteId(routeIds[0]);
        }
    };



    const handleClearChatAction = () => {
        clearChatHistory();
    };

    const handleSatelliteView = () => {
        setMapViewMode('satellite');
    };

    const handleStreetView = () => {
        setMapViewMode('street');
    };

    const handlePlanningResult = (data: any) => {
        useAppStore.getState().applyPlanningMapPlan(data);
    };

    const handleDisplayRouteAction = (data: any) => {
        if (!data || !data.optimal_routes || data.optimal_routes.length === 0) return;

        const routeData = data; // Full response from calculate_route
        // Backend puts optimal at 0 or we check isOptimal

        // Use route_id from backend if available, else generate one
        const routeId = routeData.route_id || Date.now();
        const displayId = `Route ${Object.keys(activeRoutes).length + 1}`;

        const newRoute = {
            id: routeId,
            displayId: displayId,
            source: routeData.source,
            destination: routeData.destination,
            intermediates: [], // TODO: Extract if available in response
            waypoints: [routeData.source, routeData.destination], // Simplified
            created: new Date(),
            routeData: {
                ...routeData,
                route_cost: routeData.route_cost ? Number(routeData.route_cost).toFixed(2) : null,
                objective: routeData.objective || null
            }
        };

        addActiveRoute(newRoute);
        // Trigger zoom to new route
        const { setLastCreatedRouteId } = useAppStore.getState();
        setLastCreatedRouteId(routeId);
    };

    // const handleAssignVehicleAction = (data: any) => {
    //     // NEW: Extract nested data
    //     const assignmentData = data.data || data;  // Support both old and new format

    //     if (!assignmentData || !assignmentData.vehicle_id) {
    //         console.error('Invalid assignment data:', data);
    //         return;
    //     }

    //     const vehicleId = assignmentData.vehicle_id;
    //     const routeId = assignmentData.route_id;

    //     // console.log(`🚗 Assigning vehicle ${vehicleId} to route ${routeId}`);

    //     const vehicle = vehicles.find(v => v.id === vehicleId);
    //     const route = activeRoutes[routeId];

    //     if (!vehicle) {
    //         // console.error(`Vehicle ${vehicleId} not found`);
    //         return;
    //     }

    //     if (!route) {
    //         // console.error(`Route ${routeId} not found`);
    //         return;
    //     }

    //     // console.log(`Found vehicle: ${vehicle.label}, route: ${route.source} → ${route.destination}`);

    //     // Update vehicle with assignment
    //     updateVehicle({
    //         ...vehicle,
    //         status: 'assigned',
    //         is_available: false,
    //         current_location: route.source,
    //         current_position: route.routeData?.source_coords || route.routeData?.optimal_routes?.[0]?.path?.[0],
    //         departure_time: assignmentData.departure_time,
    //         arrival_time: assignmentData.arrival_time,
    //         assigned_route: {
    //             route_id: routeId,
    //             route_data: route.routeData,
    //             waypoints: route.waypoints,
    //             source: route.source,
    //             destination: route.destination,
    //             intermediate_locations: route.intermediates,
    //             assigned_at: new Date().toISOString(),
    //             vehicle_type: assignmentData.vehicle_type || vehicle.type,
    //             vehicle_details: assignmentData.vehicle_detials || assignmentData.vehicle_details || {},  // Note backend typo: "detials"
    //             route_cost: assignmentData.route_cost ? Number(assignmentData.route_cost).toFixed(2) : null,
    //             distance: assignmentData.distance || null,
    //             departure_time: assignmentData.departure_time,
    //             arrival_time: assignmentData.arrival_time,
    //         }
    //     });
    //     // Trigger zoom to the assigned route
    //     const { setLastAssignedRouteId } = useAppStore.getState();
    //     setLastAssignedRouteId(routeId);

    //     // console.log(`✅ Vehicle ${vehicleId} assigned to route ${routeId}`);
    // };

    const handleAssignVehicleAction = (data: any) => {
        // NEW: Support for multiple vehicle assignment
        const assignmentData = data.data || data;  // Support both old and new format

        const routeId = assignmentData.route_id;
        const route = activeRoutes[routeId];

        if (!route) {
            console.error(`Route ${routeId} not found`);
            return;
        }

        // Decode polyline path to {lat,lng}[] for AnimatedVehicleMarker
        const routeDataForVehicle = JSON.parse(JSON.stringify(route.routeData));
        if (routeDataForVehicle?.optimal_routes?.[0]?.path && typeof routeDataForVehicle.optimal_routes[0].path === 'string') {
            routeDataForVehicle.optimal_routes[0].path = decodePolyline(routeDataForVehicle.optimal_routes[0].path);
        }

        const startPosition = route.routeData?.source_coords
            || routeDataForVehicle?.optimal_routes?.[0]?.path?.[0]
            || { lat: 0, lng: 0 };

        // Check if new multi-vehicle format (has assigned_vehicles array)
        if (assignmentData.assigned_vehicles && Array.isArray(assignmentData.assigned_vehicles)) {
            // --- MULTI-VEHICLE ASSIGNMENT (staggered so they animate one after another) ---
            const STAGGER_DELAY_MS = 5000; // 3 seconds between each vehicle start

            assignmentData.assigned_vehicles.forEach((assignedVehicle: any, index: number) => {
                const vehicleId = assignedVehicle.vehicle_id;
                const vehicle = vehicles.find(v => v.id === vehicleId);

                if (!vehicle) {
                    console.error(`Vehicle ${vehicleId} not found`);
                    return;
                }

                const assignVehicle = () => {
                    updateVehicle({
                        ...vehicle,
                        status: 'assigned',
                        is_available: false,
                        current_location: route.source,
                        current_position: startPosition,
                        departure_time: assignedVehicle.departure_time || assignmentData.departure_time,
                        arrival_time: assignedVehicle.arrival_time || assignmentData.arrival_time,
                        capacity: assignedVehicle.capacity_kg || vehicle.capacity,
                        vehicle_details: assignedVehicle.vehicle_details || vehicle.vehicle_details,
                        assigned_route: {
                            route_id: routeId,
                            route_data: routeDataForVehicle,
                            waypoints: route.waypoints,
                            source: route.source,
                            destination: route.destination,
                            intermediate_locations: route.intermediates,
                            assigned_at: new Date().toISOString(),
                            vehicle_type: assignedVehicle.vehicle_type || vehicle.type,
                            vehicle_details: assignedVehicle.vehicle_details || {},
                            route_cost: assignedVehicle.cost_per_km ? String(assignedVehicle.cost_per_km) : null,
                            distance: assignmentData.distance || null,
                            departure_time: assignedVehicle.departure_time || assignmentData.departure_time,
                            arrival_time: assignedVehicle.arrival_time || assignmentData.arrival_time,
                        }
                    });
                };

                // First vehicle starts immediately, subsequent ones staggered
                if (index === 0) {
                    assignVehicle();
                } else {
                    setTimeout(assignVehicle, index * STAGGER_DELAY_MS);
                }
            });

            // Trigger zoom to the assigned route
            const { setLastAssignedRouteId } = useAppStore.getState();
            setLastAssignedRouteId(routeId);

        } else {
            // --- LEGACY SINGLE-VEHICLE ASSIGNMENT (backward compatible) ---
            if (!assignmentData.vehicle_id) {
                console.error('Invalid assignment data:', data);
                return;
            }

            const vehicleId = assignmentData.vehicle_id;
            const vehicle = vehicles.find(v => v.id === vehicleId);

            if (!vehicle) {
                return;
            }

            updateVehicle({
                ...vehicle,
                status: 'assigned',
                is_available: false,
                current_location: route.source,
                current_position: startPosition,
                departure_time: assignmentData.departure_time,
                arrival_time: assignmentData.arrival_time,
                assigned_route: {
                    route_id: routeId,
                    route_data: routeDataForVehicle,
                    waypoints: route.waypoints,
                    source: route.source,
                    destination: route.destination,
                    intermediate_locations: route.intermediates,
                    assigned_at: new Date().toISOString(),
                    vehicle_type: assignmentData.vehicle_type || vehicle.type,
                    vehicle_details: assignmentData.vehicle_detials || assignmentData.vehicle_details || {},
                    route_cost: assignmentData.route_cost ? Number(assignmentData.route_cost).toFixed(2) : null,
                    distance: assignmentData.distance || null,
                    departure_time: assignmentData.departure_time,
                    arrival_time: assignmentData.arrival_time,
                }
            });

            // Trigger zoom to the assigned route
            const { setLastAssignedRouteId } = useAppStore.getState();
            setLastAssignedRouteId(routeId);
        }
    };

    const handleRemoveRouteAction = (data: any) => {
        if (!data || !data.route_id) return;

        const routeId = data.route_id;

        // Find the route using flexible comparison
        const routeToRemove = Object.values(activeRoutes).find(
            r => String(r.id) === String(routeId) || Number(r.id) === Number(routeId)
        );

        if (routeToRemove) {
            // console.log(`🗑️ Removing route ${routeId}`);

            // Use the actual ID from the route object for removal
            removeActiveRoute(routeToRemove.id);

            // Reset vehicles assigned to this route
            vehicles.forEach(v => {
                if (v.assigned_route?.route_data && v.status === 'assigned') {
                    const vehicleRouteId = v.assigned_route.route_data?.route_id;
                    if (vehicleRouteId &&
                        (String(vehicleRouteId) === String(routeId) ||
                            Number(vehicleRouteId) === Number(routeId))) {
                        updateVehicle({
                            ...v,
                            status: 'available',
                            is_available: true,
                            assigned_route: undefined
                        });
                    }
                }
            });

            // console.log(`✅ Route ${routeId} removed`);
        } else {
            // console.warn(`Route ${routeId} not found in activeRoutes`);
        }
    };


    // const handleAlternativeRouteAction = (data: any) => {
    //     if (!data || !data.alternative_route) return;

    //     // The backend returns the new alternative route with route_id
    //     const altRouteId = data.route_id;
    //     const newRoute = {
    //         id: altRouteId,
    //         displayId: `Route ${Object.keys(activeRoutes).length + 1} (Alt)`,
    //         source: data.waypoints?.[0] || '',
    //         destination: data.waypoints?.[data.waypoints?.length - 1] || '',
    //         intermediates: data.waypoints?.slice(1, -1) || [],
    //         waypoints: data.waypoints || [],
    //         created: new Date(),
    //         routeData: {
    //             optimal_routes: [data.alternative_route],
    //             route_id: altRouteId,
    //             source: data.waypoints?.[0],
    //             destination: data.waypoints?.[data.waypoints?.length - 1]
    //         }
    //     };

    //     addActiveRoute(newRoute);
    // };

    //     const handleAlternativeRouteAction = (data: any) => {
    //         const routeId = data.route_id;
    //         const existingRoute = activeRoutes[routeId];

    //         if (existingRoute) {
    //             // Remove the old route first
    //             removeActiveRoute(routeId);

    //             // Add the alternative route as a new route
    //             const newRouteId = Date.now(); // Generate new ID
    //             addActiveRoute({
    //                 id: newRouteId,
    //                 source: existingRoute.source,
    //                 destination: existingRoute.destination,
    //                 waypoints: existingRoute.waypoints,
    //                 intermediates: existingRoute.intermediates,
    //                 created: new Date(),
    //                 routeData: {
    //                     ...data,
    //                     route_id: newRouteId
    //       }
    //     });
    //   }
    // };

    // const handleAlternativeRouteAction = (data: any) => {
    //     // Extract IDs
    //     const newRouteId = data.route_id;           // 82 (new route)
    //     const parentRouteId = parseInt(data.parent_route_id);  // 81 (old route to remove)

    //     // Get the old route that needs to be replaced
    //     const oldRoute = activeRoutes[parentRouteId];

    //     if (!oldRoute) {
    //         console.error(`Parent route ${parentRouteId} not found for alternative`);
    //         return;
    //     }

    //     console.log(`🔄 Replacing route ${parentRouteId} with alternative route ${newRouteId}`);

    //     // 1. Remove the old route from map and dashboard
    //     removeActiveRoute(parentRouteId);

    //     // 2. Extract route information
    //     const waypoints = data.waypoints || [];
    //     const source = waypoints[0] || oldRoute.source;
    //     const destination = waypoints[waypoints.length - 1] || oldRoute.destination;
    //     const intermediates = waypoints.slice(1, -1);

    //     // 3. Create new route with alternative route data
    //     const newRoute = {
    //         id: newRouteId,
    //         source: source,
    //         destination: destination,
    //         waypoints: waypoints,
    //         intermediates: intermediates,
    //         created: new Date(),
    //         routeData: {
    //             route_id: newRouteId,
    //             source: source,
    //             destination: destination,
    //             optimal_routes: [data.alternative_route],  // Use the alternative_route object
    //             reason: data.reason || 'Alternative route'
    //         }
    //     };

    //     // 4. Add the new alternative route to map and dashboard
    //     addActiveRoute(newRoute);

    //     console.log(`✅ Alternative route ${newRouteId} added successfully`);
    // };
    const handleAlternativeRouteAction = (data: any) => {
        // Extract IDs
        const newRouteId = data.route_id;           // 82 (new route)
        const parentRouteId = parseInt(data.parent_route_id);  // 81 (old route to remove)

        // Get the old route that needs to be replaced
        const oldRoute = activeRoutes[parentRouteId];



        // console.log(`🔄 Replacing route ${parentRouteId} with alternative route ${newRouteId}`);

        // 1. Remove the old route from map and dashboard
        //removeActiveRoute(parentRouteId);
        markRouteAsInactive(parentRouteId);

        // 2. Find and reassign vehicles from old route to new route
        const vehiclesOnOldRoute = vehicles.filter(
            v => v.assigned_route?.route_data?.route_id === parentRouteId
        );

        // console.log(`🚗 Found ${vehiclesOnOldRoute.length} vehicles on route ${parentRouteId}`);

        // 3. Extract route information
        const waypoints = data.waypoints || [];
        const source = waypoints[0] || oldRoute.source;
        const destination = waypoints[waypoints.length - 1] || oldRoute.destination;
        const intermediates = waypoints.slice(1, -1);

        // 4. Create new route with alternative route data
        // console.log('📊 Alternative route data.route_cost:', data.route_cost);

        const newRoute = {
            id: newRouteId,
            source: source,
            destination: destination,
            waypoints: waypoints,
            intermediates: intermediates,
            created: new Date(),
            isActive: true,
            routeData: {
                route_id: newRouteId,
                source: source,
                destination: destination,
                optimal_routes: [data.alternative_route],  // Use the alternative_route object
                reason: data.reason || 'Alternative route',
                route_cost: data.route_cost ? Number(data.route_cost).toFixed(2) : null
            }
        };

        // console.log('📊 Stored route_cost in routeData:', newRoute.routeData.route_cost);

        // 5. Add the new alternative route to map and dashboard
        addActiveRoute(newRoute);

        // 6. Reassign vehicles to the new alternative route
        vehiclesOnOldRoute.forEach(vehicle => {
            //console.log(`🔓 Making vehicle ${vehicle.id} available (was on route ${parentRouteId})`);

            updateVehicle({
                ...vehicle,
                status: 'available',
                is_available: true,
                assigned_route: undefined,
                current_location: vehicle.assigned_route?.source || vehicle.current_location
            });
        });

        // if (vehiclesOnOldRoute.length > 0) {
        //     console.log(`✅ Reassigned ${vehiclesOnOldRoute.length} vehicles to alternative route ${newRouteId}`);
        // }

        // console.log(`✅ Alternative route ${newRouteId} added successfully`);
    };



    const handleResetVehicleAction = (data: any) => {
        if (!data || !data.vehicle_id) return;

        const vehicle = vehicles.find(v => v.id === data.vehicle_id);
        if (vehicle) {
            updateVehicle({
                ...vehicle,
                status: 'available',
                is_available: true,
                assigned_route: undefined
            });
        }
    };

    const handleMultimodalRouteAction = (data: any) => {
        if (!data || !data.data) return;

        const multimodalData = data.data;
        const routeId = data.route_id || Date.now();

        // Store multimodal route with special flag
        const newRoute = {
            id: routeId,
            displayId: `Route ${Object.keys(activeRoutes).length + 1}`,
            source: data.source || multimodalData.segment_1?.source || '',
            destination: data.destination || multimodalData.segment_3?.destination || '',
            intermediates: [],
            waypoints: [data.source, data.destination],
            created: new Date(),
            isActive: true,
            isMultimodal: true,  // Flag to identify multimodal routes
            routeData: {
                route_id: routeId,
                source: data.source,
                destination: data.destination,
                multimodal: true,
                segments: multimodalData,  // Store all segments
                // Use backend-provided total_cost
                route_cost: (multimodalData.total_cost ?? data.total_cost)?.toFixed?.(2) ??
                    Number(multimodalData.total_cost ?? data.total_cost).toFixed(2),
                // Calculate total duration
                total_duration: multimodalData.total_duration,
                // Calculate total distance (road only)
                total_distance: multimodalData.total_distance_km.toFixed(2),
                objective: multimodalData.objective || null,
                cached: data.cached !== undefined ? data.cached : undefined
            }
        };

        addActiveRoute(newRoute);
        // Trigger zoom to new multimodal route
        const { setLastCreatedRouteId } = useAppStore.getState();
        setLastCreatedRouteId(routeId);
    };

    // const handleMultimodalAssignVehicle = async (action: any) => {
    //     const routeId = action?.route_id;
    //     if (!routeId) {
    //         console.error('No route_id provided in action');
    //         addChatMessage('assistant', 'No route ID provided. Please specify which route to assign vehicles to.');
    //         return;
    //     }
    //     // Find the multimodal route by ID
    //     const multimodalRoute = activeRoutes[routeId];

    //     if (!multimodalRoute || !multimodalRoute.routeData?.multimodal) {
    //         console.error(`Multimodal route ${routeId} not found`);
    //         addChatMessage('assistant', `Multimodal route ${routeId} not found. Please plan the route first.`);
    //         return;
    //     }

    //     try {
    //         // Call the API to assign vehicles
    //         const response = await vehiclesApi.assignMultimodal(routeId);

    //         if (response.status === 'success' && response.assigned_vehicles) {
    //             const assignedVehicles = response.assigned_vehicles;

    //             // Handle Segment 1 vehicle assignment
    //             if (assignedVehicles.segment_1) {
    //                 const segment1Data = assignedVehicles.segment_1;
    //                 const vehicleId = segment1Data.vehicle_id;
    //                 const vehicle = vehicles.find(v => v.id === vehicleId);

    //                 if (vehicle) {
    //                     // Get segment 1 path from stored route data
    //                     const segment1Path = multimodalRoute.routeData?.segments?.segment_1?.path;
    //                     const startCoords = segment1Path?.[0];

    //                     updateVehicle({
    //                         ...vehicle,
    //                         status: 'assigned',
    //                         is_available: false,
    //                         current_location: segment1Data.start_location,
    //                         current_position: startCoords || vehicle.current_position,
    //                         assigned_route: {
    //                             route_id: multimodalRoute.id,
    //                             route_data: {
    //                                 route_id: multimodalRoute.id,
    //                                 optimal_routes: [{
    //                                     path: segment1Path,
    //                                     distance: multimodalRoute.routeData?.segments?.segment_1?.distance,
    //                                     duration: multimodalRoute.routeData?.segments?.segment_1?.duration,
    //                                     isOptimal: true
    //                                 }]
    //                             },
    //                             waypoints: [segment1Data.start_location, segment1Data.end_location],
    //                             source: segment1Data.start_location,
    //                             destination: segment1Data.end_location,
    //                             intermediate_locations: [],
    //                             assigned_at: segment1Data.assigned_at,
    //                             vehicle_type: segment1Data.vehicle_type,
    //                             vehicle_details: {},
    //                             route_cost: segment1Data.route_cost?.toString() || null,
    //                             distance: multimodalRoute.routeData?.segments?.segment_1?.distance || null
    //                         }
    //                     });

    //                     console.log(`✅ Vehicle ${vehicleId} assigned to segment 1`);
    //                 }
    //             }

    //             // Handle Segment 3 vehicle assignment (if exists)
    //             if (assignedVehicles.segment_3) {
    //                 const segment3Data = assignedVehicles.segment_3;
    //                 const vehicleId = segment3Data.vehicle_id;
    //                 const vehicle = vehicles.find(v => v.id === vehicleId);

    //                 if (vehicle) {
    //                     // Get segment 3 path from stored route data
    //                     const segment3Path = multimodalRoute.routeData?.segments?.segment_3?.path;
    //                     const startCoords = segment3Path?.[0];

    //                     updateVehicle({
    //                         ...vehicle,
    //                         status: 'assigned',
    //                         is_available: false,
    //                         current_location: segment3Data.start_location,
    //                         current_position: startCoords || vehicle.current_position,
    //                         assigned_route: {
    //                             route_id: multimodalRoute.id,
    //                             route_data: {
    //                                 route_id: multimodalRoute.id,
    //                                 optimal_routes: [{
    //                                     path: segment3Path,
    //                                     distance: multimodalRoute.routeData?.segments?.segment_3?.distance,
    //                                     duration: multimodalRoute.routeData?.segments?.segment_3?.duration,
    //                                     isOptimal: true
    //                                 }]
    //                             },
    //                             waypoints: [segment3Data.start_location, segment3Data.end_location],
    //                             source: segment3Data.start_location,
    //                             destination: segment3Data.end_location,
    //                             intermediate_locations: [],
    //                             assigned_at: segment3Data.assigned_at,
    //                             vehicle_type: segment3Data.vehicle_type,
    //                             vehicle_details: {},
    //                             route_cost: segment3Data.route_cost?.toString() || null,
    //                             distance: multimodalRoute.routeData?.segments?.segment_3?.distance || null
    //                         }
    //                     });

    //                     console.log(`✅ Vehicle ${vehicleId} assigned to segment 3`);
    //                 }
    //             }

    //             //addChatMessage('assistant', `Vehicles assigned to multimodal route ${multimodalRoute.id}. Animation will begin shortly.`);
    //         }
    //     } catch (error: any) {
    //         console.error('Failed to assign multimodal vehicles:', error);
    //         addChatMessage('assistant', `Failed to assign vehicles: ${error.message || 'Unknown error'}`);
    //     }
    // };

    const handleMultimodalAssignVehicle = async (action: any) => {
        const routeId = action?.route_id;
        const assignmentData = action?.data;

        if (!routeId) {
            console.error('No route_id provided in action');
            addChatMessage('assistant', 'No route ID provided. Please specify which route to assign vehicles to.');
            return;
        }

        if (!assignmentData || assignmentData.status !== 'success') {
            console.error('Invalid assignment data in action');
            addChatMessage('assistant', 'Failed to get vehicle assignment data.');
            return;
        }

        // Find the multimodal route by ID
        const multimodalRoute = activeRoutes[routeId];

        if (!multimodalRoute || !multimodalRoute.routeData?.multimodal) {
            console.error(`Multimodal route ${routeId} not found`);
            addChatMessage('assistant', `Multimodal route ${routeId} not found. Please plan the route first.`);
            return;
        }

        // Handle Segment 1 vehicle assignment
        if (assignmentData.segment_1) {
            const segment1Data = assignmentData.segment_1;
            const vehicleId = segment1Data.vehicle_id;
            const vehicle = vehicles.find(v => v.id === vehicleId);

            if (vehicle) {
                // Get segment 1 path from stored route data
                const segment1Path = multimodalRoute.routeData?.segments?.segment_1?.path;
                const startCoords = segment1Path?.[0];

                updateVehicle({
                    ...vehicle,
                    status: 'assigned',
                    is_available: false,
                    current_location: segment1Data.start_location,
                    current_position: startCoords || vehicle.current_position,
                    departure_time: assignmentData.departure_time,
                    arrival_time: assignmentData.arrival_time,
                    assigned_route: {
                        route_id: multimodalRoute.id,
                        //isMultimodalSegment: true,
                        route_data: {
                            route_id: multimodalRoute.id,
                            optimal_routes: [{
                                path: segment1Path,
                                distance: multimodalRoute.routeData?.segments?.segment_1?.distance,
                                duration: multimodalRoute.routeData?.segments?.segment_1?.duration,
                                isOptimal: true
                            }]
                        },
                        waypoints: [segment1Data.start_location, segment1Data.end_location],
                        source: segment1Data.start_location,
                        destination: segment1Data.end_location,
                        intermediate_locations: [],
                        assigned_at: segment1Data.assigned_at,
                        vehicle_type: segment1Data.vehicle_type,
                        vehicle_details: {
                            speed: action.data?.vehicle_detials?.speed || action.data?.vehicle_details?.speed,
                            capacity: action.data?.vehicle_detials?.capacity || action.data?.vehicle_details?.capacity,
                            fuel_type: action.data?.vehicle_detials?.fuel_type || action.data?.vehicle_details?.fuel_type,
                            fuel_consumption: action.data?.vehicle_detials?.fuel_consumption || action.data?.vehicle_details?.fuel_consumption,
                            fuel_price: action.data?.vehicle_detials?.fuel_price || action.data?.vehicle_details?.fuel_price,
                        },
                        route_cost: segment1Data.route_cost?.toString() || null,
                        distance: multimodalRoute.routeData?.segments?.segment_1?.distance || null
                    }
                });

                console.log(`✅ Vehicle ${vehicleId} assigned to segment 1`);
            }
        }

        // Handle Segment 3 vehicle assignment (if exists)
        if (assignmentData.segment_3) {
            const segment3Data = assignmentData.segment_3;
            const vehicleId = segment3Data.vehicle_id;
            const vehicle = vehicles.find(v => v.id === vehicleId);

            if (vehicle) {
                // Get segment 3 path from stored route data
                const segment3Path = multimodalRoute.routeData?.segments?.segment_3?.path;
                const startCoords = segment3Path?.[0];

                updateVehicle({
                    ...vehicle,
                    status: 'assigned',
                    is_available: false,
                    current_location: segment3Data.start_location,
                    current_position: startCoords || vehicle.current_position,
                    assigned_route: {
                        route_id: multimodalRoute.id,
                        route_data: {
                            route_id: multimodalRoute.id,
                            optimal_routes: [{
                                path: segment3Path,
                                distance: multimodalRoute.routeData?.segments?.segment_3?.distance,
                                duration: multimodalRoute.routeData?.segments?.segment_3?.duration,
                                isOptimal: true
                            }]
                        },
                        waypoints: [segment3Data.start_location, segment3Data.end_location],
                        source: segment3Data.start_location,
                        destination: segment3Data.end_location,
                        intermediate_locations: [],
                        assigned_at: segment3Data.assigned_at,
                        vehicle_type: segment3Data.vehicle_type,
                        vehicle_details: {},
                        route_cost: segment3Data.route_cost?.toString() || null,
                        distance: multimodalRoute.routeData?.segments?.segment_3?.distance || null
                    }
                });

                console.log(`✅ Vehicle ${vehicleId} assigned to segment 3`);
            }
        }
    };

    const handleConnectHubAction = (data: any) => {
        if (!data || !data.routes || data.routes.length === 0) {
            console.warn('No routes in connect_hub response');
            return;
        }

        console.log(`🔗 Connecting hub: ${data.hub} with ${data.total_routes} routes`);

        // Loop through each route in the response and add it
        data.routes.forEach((routeItem: any) => {
            const routeId = routeItem.route_id;
            const routeData = routeItem.route?.data;

            if (!routeData) {
                console.warn(`Missing route data for route ${routeId}`);
                return;
            }

            // Create the ActiveRoute object (same structure as multimodal_route)
            const newRoute = {
                id: routeId,
                source: routeItem.source,
                destination: routeItem.destination,
                intermediates: [],
                waypoints: [routeItem.source, routeItem.destination],
                created: new Date(),
                isActive: true,
                routeData: {
                    multimodal: true,
                    segments: {
                        segment_1: routeData.segment_1,
                        segment_2: routeData.segment_2,
                        segment_3: routeData.segment_3
                    },
                    total_distance: routeData.total_distance_km,
                    total_duration: routeData.total_duration,
                    route_cost: routeData.total_cost ?? routeItem.total_cost,
                    route_id: routeId,
                    cached: routeItem.cached !== undefined ? routeItem.cached : undefined
                }
            };

            addActiveRoute(newRoute);
            console.log(`✅ Added route ${routeId}: ${routeItem.source} → ${routeItem.destination}`);
        });
    };

    // const handleWarehouseStatusUpdate = (data: any) => {
    //     if (!data || !data.success || !data.data) {
    //         console.warn('Invalid warehouse status update data:', data);
    //         return;
    //     }

    //     const warehouseData = data.data;
    //     const warehouseId = warehouseData.warehouse_id;
    //     const isActive = warehouseData.is_active;

    //     console.log(`🏭 Updating warehouse ${warehouseData.warehouse_name} (ID: ${warehouseId}) - Active: ${isActive}`);

    //     updateWarehouse(warehouseId, { is_active: isActive ? 1 : 0 });

    //     console.log(`✅ Warehouse ${warehouseData.warehouse_name} status updated to ${isActive ? 'active' : 'inactive'}`);
    // };

    const handleWarehouseStatusUpdate = (data: any) => {
        if (!data) {
            console.log('Invalid warehouse status update data:', data);
            return;
        }

        const warehouseData = data;
        const warehouseId = warehouseData.warehouse_id;
        const isActive = warehouseData.is_active;

        console.log(`🏭 Updating warehouse ${warehouseData.warehouse_name} (ID: ${warehouseId}) - Active: ${isActive}`);

        // Update with boolean converted to number (1 or 0)
        updateWarehouse(warehouseId, { is_active: isActive ? 1 : 0 });

        console.log(`✅ Warehouse ${warehouseData.warehouse_name} status updated`);
    };

    const handleResetAllVehicles = () => {
        // Get all vehicles that are currently assigned
        const assignedVehicles = vehicles.filter(v => v.status === 'assigned' || v.assigned_route);

        if (assignedVehicles.length === 0) {
            console.log('No assigned vehicles to reset');
            return;
        }

        console.log(`🔄 Resetting ${assignedVehicles.length} vehicles...`);

        // Reset each assigned vehicle to available state
        assignedVehicles.forEach(vehicle => {
            updateVehicle({
                ...vehicle,
                status: 'available',
                is_available: true,
                assigned_route: undefined
            });
        });

        console.log(`✅ All vehicles reset to available state`);
    };

    // const handleAssignPlaneAction = (action: any) => {
    //     const routeId = action?.route_id;
    //     const assignmentData = action?.data;

    //     if (!routeId) {
    //         console.error('No route_id provided in assign_plane action');
    //         addChatMessage('assistant', 'No route ID provided for plane assignment.');
    //         return;
    //     }

    //     if (!assignmentData || assignmentData.status !== 'success') {
    //         console.error('Invalid assignment data in assign_plane action');
    //         addChatMessage('assistant', 'Failed to get plane assignment data.');
    //         return;
    //     }

    //     // Get segment_2 data (plane flight segment)
    //     const segment2Data = assignmentData.segment_2;
    //     if (!segment2Data) {
    //         console.error('No segment_2 data in assign_plane response');
    //         return;
    //     }

    //     const vehicleDetails = assignmentData.vehicle_details;
    //     const planeVehicleId = segment2Data.vehicle_id;

    //     // Find the plane vehicle in the store
    //     const planeVehicle = vehicles.find(v => v.id === planeVehicleId);

    //     if (planeVehicle) {
    //         // Update plane vehicle status to 'assigned'
    //         updateVehicle({
    //             ...planeVehicle,
    //             status: 'assigned',
    //             is_available: false,
    //             type: 'plane' as any, // Mark as plane type
    //             current_location: segment2Data.start_location,
    //             current_position: {
    //                 lat: segment2Data.start_coords.lat,
    //                 lng: segment2Data.start_coords.lng
    //             },
    //             departure_time: assignmentData.departure_time || segment2Data.departure_time,
    //             arrival_time: assignmentData.arrival_time || segment2Data.arrival_time,
    //             capacity: segment2Data.vehicle_capacity,
    //             vehicle_details: {
    //                 speed: vehicleDetails?.speed || 800,
    //                 fuel_type: vehicleDetails?.fuel_type || 'ATF',
    //                 fuel_consumption: vehicleDetails?.fuel_consumption || 0.3,
    //                 fuel_price: vehicleDetails?.fuel_price || 0.9,
    //             },
    //             assigned_route: {
    //                 route_id: routeId,
    //                 route_data: {
    //                     route_id: routeId,
    //                     optimal_routes: [] // Planes don't use road paths
    //                 },
    //                 waypoints: [segment2Data.start_location, segment2Data.end_location],
    //                 source: segment2Data.start_location,
    //                 destination: segment2Data.end_location,
    //                 intermediate_locations: [],
    //                 assigned_at: segment2Data.assigned_at,
    //                 vehicle_type: 'plane',
    //                 vehicle_details: {
    //                     speed: vehicleDetails?.speed || 800,
    //                     fuel_type: vehicleDetails?.fuel_type || 'ATF',
    //                     fuel_consumption: vehicleDetails?.fuel_consumption,
    //                     fuel_price: vehicleDetails?.fuel_price,
    //                 },
    //                 route_cost: segment2Data.route_cost?.toString() || null,
    //                 distance: null,
    //                 departure_time: segment2Data.departure_time,
    //                 arrival_time: segment2Data.arrival_time,
    //             }
    //         });

    //         console.log(`✅ Plane ${planeVehicleId} assigned to route ${routeId}`);
    //     }

    //     // Start plane animation - add to activePlanes store
    //     const { addPlane } = useAppStore.getState();

    //     addPlane({
    //         id: `plane-${routeId}-${Date.now()}`,
    //         routeId: routeId,
    //         sourceAirport: {
    //             lat: segment2Data.start_coords.lat,
    //             lng: segment2Data.start_coords.lng,
    //             name: segment2Data.start_location
    //         },
    //         destAirport: {
    //             lat: segment2Data.end_coords.lat,
    //             lng: segment2Data.end_coords.lng,
    //             name: segment2Data.end_location
    //         },
    //         currentPosition: {
    //             lat: segment2Data.start_coords.lat,
    //             lng: segment2Data.start_coords.lng
    //         },
    //         status: 'flying'
    //     });

    //     console.log(`✈️ Plane animation started: ${segment2Data.start_location} → ${segment2Data.end_location}`);
    // };

    // --- Legacy / Helper Handlers (kept if needed for manual triggers) ---
    const handleAssignPlaneAction = (action: any) => {
        const routeId = action?.route_id;
        const assignmentData = action?.data;

        if (!routeId) {
            console.error('No route_id provided in assign_plane action');
            addChatMessage('assistant', 'No route ID provided for plane assignment.');
            return;
        }

        if (!assignmentData || !assignmentData.success) {
            console.error('Invalid assignment data in assign_plane action');
            addChatMessage('assistant', 'Failed to get plane assignment data.');
            return;
        }

        // NEW: data.data is now an array of plane assignments
        const planeAssignments = assignmentData.data;
        if (!planeAssignments || !Array.isArray(planeAssignments) || planeAssignments.length === 0) {
            // Fallback: try old segment_2 format
            const segment2Data = assignmentData.segment_2;
            if (segment2Data) {
                // --- LEGACY SINGLE PLANE (old format with segment_2) ---
                const vehicleDetails = assignmentData.vehicle_details;
                const planeVehicleId = segment2Data.vehicle_id;
                const planeVehicle = vehicles.find(v => v.id === planeVehicleId);

                if (planeVehicle) {
                    updateVehicle({
                        ...planeVehicle,
                        status: 'assigned',
                        is_available: false,
                        type: 'plane' as any,
                        current_location: segment2Data.start_location,
                        current_position: {
                            lat: segment2Data.start_coords.lat,
                            lng: segment2Data.start_coords.lng
                        },
                        departure_time: assignmentData.departure_time || segment2Data.departure_time,
                        arrival_time: assignmentData.arrival_time || segment2Data.arrival_time,
                        capacity: segment2Data.vehicle_capacity,
                        vehicle_details: {
                            speed: vehicleDetails?.speed || 800,
                            fuel_type: vehicleDetails?.fuel_type || 'ATF',
                            fuel_consumption: vehicleDetails?.fuel_consumption || 0.3,
                            fuel_price: vehicleDetails?.fuel_price || 0.9,
                        },
                        assigned_route: {
                            route_id: routeId,
                            route_data: { route_id: routeId, optimal_routes: [] },
                            waypoints: [segment2Data.start_location, segment2Data.end_location],
                            source: segment2Data.start_location,
                            destination: segment2Data.end_location,
                            intermediate_locations: [],
                            assigned_at: segment2Data.assigned_at,
                            vehicle_type: 'plane',
                            vehicle_details: {
                                speed: vehicleDetails?.speed || 800,
                                fuel_type: vehicleDetails?.fuel_type || 'ATF',
                                fuel_consumption: vehicleDetails?.fuel_consumption,
                                fuel_price: vehicleDetails?.fuel_price,
                            },
                            route_cost: segment2Data.route_cost?.toString() || null,
                            distance: null,
                            departure_time: segment2Data.departure_time,
                            arrival_time: segment2Data.arrival_time,
                        }
                    });
                }

                const { addPlane } = useAppStore.getState();
                addPlane({
                    id: `plane-${routeId}-${Date.now()}`,
                    routeId: routeId,
                    sourceAirport: {
                        lat: segment2Data.start_coords.lat,
                        lng: segment2Data.start_coords.lng,
                        name: segment2Data.start_location
                    },
                    destAirport: {
                        lat: segment2Data.end_coords.lat,
                        lng: segment2Data.end_coords.lng,
                        name: segment2Data.end_location
                    },
                    currentPosition: {
                        lat: segment2Data.start_coords.lat,
                        lng: segment2Data.start_coords.lng
                    },
                    status: 'flying'
                });
                return;
            }

            console.error('No plane assignment data found');
            return;
        }

        // --- NEW MULTI-PLANE ASSIGNMENT (array format) ---
        const { addPlane } = useAppStore.getState();

        planeAssignments.forEach((planeData: any) => {
            const planeVehicleId = planeData.vehicle_id;
            const planeVehicle = vehicles.find(v => v.id === planeVehicleId);
            const vehicleDetails = planeData.vehicle_details;

            if (planeVehicle) {
                updateVehicle({
                    ...planeVehicle,
                    status: 'assigned',
                    is_available: false,
                    type: 'plane' as any,
                    current_location: planeData.start_location,
                    current_position: {
                        lat: planeData.start_coords.lat,
                        lng: planeData.start_coords.lng
                    },
                    departure_time: planeData.departure_time,
                    arrival_time: planeData.arrival_time,
                    capacity: planeData.vehicle_capacity,
                    vehicle_details: {
                        speed: vehicleDetails?.speed || 800,
                        fuel_type: vehicleDetails?.fuel_type || 'ATF',
                        fuel_consumption: vehicleDetails?.fuel_consumption || 0.3,
                        fuel_price: vehicleDetails?.fuel_price || 0.9,
                    },
                    assigned_route: {
                        route_id: routeId,
                        route_data: { route_id: routeId, optimal_routes: [] },
                        waypoints: [planeData.start_location, planeData.end_location],
                        source: planeData.start_location,
                        destination: planeData.end_location,
                        intermediate_locations: [],
                        assigned_at: planeData.assigned_at || new Date().toISOString(),
                        vehicle_type: 'plane',
                        vehicle_details: {
                            speed: vehicleDetails?.speed || 800,
                            fuel_type: vehicleDetails?.fuel_type || 'ATF',
                            fuel_consumption: vehicleDetails?.fuel_consumption,
                            fuel_price: vehicleDetails?.fuel_price,
                        },
                        route_cost: planeData.route_cost?.toString() || null,
                        distance: null,
                        departure_time: planeData.departure_time,
                        arrival_time: planeData.arrival_time,
                    }
                });

                console.log(`✅ Plane ${planeVehicleId} assigned to route ${routeId}`);
            }

            // Start plane animation for each plane
            addPlane({
                id: `plane-${routeId}-${planeVehicleId}-${Date.now()}`,
                routeId: routeId,
                sourceAirport: {
                    lat: planeData.start_coords.lat,
                    lng: planeData.start_coords.lng,
                    name: planeData.start_location
                },
                destAirport: {
                    lat: planeData.end_coords.lat,
                    lng: planeData.end_coords.lng,
                    name: planeData.end_location
                },
                currentPosition: {
                    lat: planeData.start_coords.lat,
                    lng: planeData.start_coords.lng
                },
                status: 'flying'
            });

            console.log(`✈️ Plane animation started: ${planeData.start_location} → ${planeData.end_location}`);
        });
    };


    const handleClearMap = async () => {
        clearActiveRoutes();
        vehicles.forEach(v => {
            if (v.status === 'assigned' || v.status === 'completed') {
                updateVehicle({
                    ...v,
                    status: 'available',
                    assigned_route: undefined
                });
            }
        });
        return { message: 'Map cleared.' };
    };

    const handleVehicleStatusUpdate = (data: any) => {
        if (!data) return;

        const statusData = data;
        const vehicleId = statusData.vehicle_id;
        const isActive = statusData.is_active;

        const vehicle = vehicles.find(v => v.id === vehicleId);
        if (!vehicle) return;

        if (!isActive) {
            // Vehicle is being deactivated
            if (vehicle.status === 'assigned' && vehicle.assigned_route) {
                // Vehicle is assigned and animating - remove from map (like reset_vehicle)
                updateVehicle({
                    ...vehicle,
                    status: 'disrupted' as any,  // Frontend-only status
                    is_available: false,
                    assigned_route: undefined
                });
            } else {
                // Vehicle is not assigned - just update status to disrupted
                updateVehicle({
                    ...vehicle,
                    status: 'disrupted' as any,  // Frontend-only status
                    is_available: false
                });
            }
        } else {
            // Vehicle is being activated (is_active: true)
            // Set status back to available
            updateVehicle({
                ...vehicle,
                status: 'available',
                is_available: true
            });
        }
    };
    const handleRouteStatusUpdate = (data: any) => {
        if (!data) {
            console.log('Invalid route status update data:', data);
            return;
        }
        const routeData = data;
        const routeId = routeData.route_id;
        const isActive = routeData.is_active;
        console.log(`🛣️ Updating route ${routeId} - Active: ${isActive}`);
        const { updateActiveRouteStatus } = useAppStore.getState();
        updateActiveRouteStatus(routeId, isActive);
        console.log(`✅ Route ${routeId} status updated to ${isActive ? 'active' : 'inactive'}`);
    };

    // const handleAirIntermediateRouteAction = (data: any) => {
    //     if (!data || !data.routes || data.routes.length === 0) {
    //         console.warn('No routes in air_intermediate_route response');
    //         return;
    //     }

    //     console.log(`✈️ Air intermediate route: ${data.routes.length} legs`);

    //     // Each item in data.routes is one multimodal leg (e.g., Mumbai→Bengaluru, Bengaluru→Delhi)
    //     data.routes.forEach((leg: any, index: number) => {
    //         const routeId = leg.route_id || Date.now() + index;

    //         const newRoute = {
    //             id: routeId,
    //             displayId: `Route ${Object.keys(activeRoutes).length + 1 + index}`,
    //             source: leg.source || leg.segment_1?.source || '',
    //             destination: leg.destination || leg.segment_3?.destination || '',
    //             intermediates: [],
    //             waypoints: [leg.source, leg.destination],
    //             created: new Date(),
    //             isActive: true,
    //             isMultimodal: true,
    //             routeData: {
    //                 route_id: routeId,
    //                 source: leg.source,
    //                 destination: leg.destination,
    //                 multimodal: true,
    //                 segments: {
    //                     segment_1: leg.segment_1,
    //                     segment_2: leg.segment_2,
    //                     segment_3: leg.segment_3,
    //                 },
    //                 route_cost: (
    //                     (leg.segment_1?.route_cost || 0) +
    //                     (leg.segment_3?.route_cost || 0)
    //                 ).toFixed(2),
    //                 total_duration: leg.total_duration,
    //                 total_distance: leg.total_distance_km?.toFixed(2),
    //                 objective: leg.objective || leg.segment_1?.objective || null,
    //             },
    //         };

    //         addActiveRoute(newRoute);
    //         console.log(`✅ Added intermediate leg ${index + 1}: ${leg.source} → ${leg.destination}`);
    //     });

    //     // Zoom to the LAST leg added
    //     const lastLeg = data.routes[data.routes.length - 1];
    //     const lastRouteId = lastLeg.route_id || Date.now() + data.routes.length - 1;
    //     const { setLastCreatedRouteId } = useAppStore.getState();
    //     setLastCreatedRouteId(lastRouteId);
    // };
    const handleAirIntermediateRouteAction = (data: any) => {
        if (!data || !data.routes || data.routes.length === 0) {
            console.warn('No routes in air_intermediate_route response');
            return;
        }

        console.log(`✈️ Air intermediate route: ${data.routes.length} legs`);

        data.routes.forEach((leg: any, index: number) => {
            const routeId = leg.route_id || Date.now() + index;
            const legData = leg.data || leg;

            const newRoute = {
                id: routeId,
                displayId: `Route ${Object.keys(activeRoutes).length + 1 + index}`,
                source: leg.source || legData.source || legData.segment_1?.source || '',
                destination: leg.destination || legData.destination || legData.segment_3?.destination || '',
                intermediates: [],
                waypoints: [leg.source || legData.source, leg.destination || legData.destination],
                created: new Date(),
                isActive: true,
                isMultimodal: true,
                routeData: {
                    route_id: routeId,
                    source: leg.source || legData.source,
                    destination: leg.destination || legData.destination,
                    multimodal: true,
                    segments: {
                        segment_1: legData.segment_1,
                        segment_2: legData.segment_2,
                        segment_3: legData.segment_3,
                    },
                    route_cost: (legData.total_cost ?? leg.total_cost)?.toFixed?.(2) ??
                        Number(legData.total_cost ?? leg.total_cost).toFixed(2),
                    total_duration: legData.total_duration,
                    total_distance: legData.total_distance_km?.toFixed(2),
                    objective: legData.objective || legData.segment_1?.objective || null,
                    cached: leg.cached !== undefined ? leg.cached : undefined,
                },
            };

            addActiveRoute(newRoute);
            console.log(`✅ Added intermediate leg ${index + 1}: ${leg.source} → ${leg.destination}`);
        });

        const lastLeg = data.routes[data.routes.length - 1];
        const lastRouteId = lastLeg.route_id || Date.now() + data.routes.length - 1;
        const { setLastCreatedRouteId } = useAppStore.getState();
        setLastCreatedRouteId(lastRouteId);
    };
    return {
        processMessage,
        isProcessing,
        startNewSession,
        handleClearMap,
        handleRemoveRouteAction // Exporting this as it might be used by a "Clear Map" button
    };
};
