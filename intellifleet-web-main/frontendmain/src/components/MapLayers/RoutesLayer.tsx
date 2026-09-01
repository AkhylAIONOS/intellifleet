// import { useEffect } from 'react';
// import { Polyline, Popup, useMap } from 'react-leaflet';
// import { useAppStore } from '../../store/appStore';
// import { formatDuration } from '../../utils/formatDuration';
// import L from 'leaflet';
// import './RoutesLayer.css';

// //const ROUTE_COLORS = ['#3388ff', '#28a745', '#dc3545', '#ffc107'];

// export const RoutesLayer = () => {
//     const { activeRoutes } = useAppStore();
//     const routes = Object.values(activeRoutes);
//     const map = useMap();

//     // Auto-zoom when routes change
//     useEffect(() => {
//         if (routes.length > 0) {
//             const bounds = L.latLngBounds([]);
//             let hasValidBounds = false;

//             routes.forEach(route => {
//                 const pathData = route.routeData?.optimal_routes?.[0]?.path;
//                 if (pathData) {
//                     pathData.forEach((p: any) => {
//                         bounds.extend([p.lat, p.lng]);
//                         hasValidBounds = true;
//                     });
//                 }
//             });

//             if (hasValidBounds) {
//                 map.fitBounds(bounds, { padding: [50, 50] });
//             }
//         }
//     }, [routes, map]);

//     return (
//         <>
//             {routes.map((route) => {
//                 const pathData = route.routeData?.optimal_routes?.[0]?.path;
//                 if (!pathData) return null;

//                 const positions = pathData.map((p: any) => [p.lat, p.lng] as [number, number]);
//                 //const color = ROUTE_COLORS[index % ROUTE_COLORS.length];
//                 const optimalRoute = route.routeData?.optimal_routes?.[0];
//                 const routeCost = route.routeData?.route_cost;

//                 return (
//                     <Polyline
//                         key={route.id}
//                         positions={positions}
//                         pathOptions={{
//                             color: route.isActive === false ? '#dc3545' : '#28a745',  // Red for inactive, Green for active
//                             weight: route.isActive === false ? 4 : 5,                  // Slightly thinner for inactive
//                             opacity: route.isActive === false ? 0.6 : 0.8              // Slightly less opaque for inactive
//                         }}
//                     >
//                         <Popup>
//                             <div className="route-popup">
//                                 {/* Header */}
//                                 <div className="route-popup-header">
//                                     <h4>Route {route.id}</h4>
//                                 </div>

//                                 {/* Body */}
//                                 <div className="route-popup-body">
//                                     {/* Type */}
//                                     <div className="route-popup-section">
//                                         <div className="route-popup-label">Type:</div>
//                                         <span className="route-type-badge">
//                                             {route.routeData?.optimal_routes?.[0]?.isOptimal === false
//                                                 ? 'Alternative Route'
//                                                 : route.intermediates?.length > 0
//                                                     ? 'Multi-stop Route'
//                                                     : 'Optimal Route'}
//                                         </span>
//                                     </div>

//                                     {/* Route Path */}
//                                     <div className="route-popup-section">
//                                         <div className="route-popup-label">Route Path:</div>
//                                         <div className="route-path">
//                                             <div className="route-path-item">
//                                                 <span className="route-path-dot start"></span>
//                                                 Start: {route.source}
//                                             </div>
//                                             <span className="route-path-arrow">→</span>
//                                             <div className="route-path-item">
//                                                 <span className="route-path-dot end"></span>
//                                                 End: {route.destination}
//                                             </div>
//                                         </div>
//                                     </div>

//                                     {/* Stats Grid */}
//                                     <div className="route-stats">
//                                         <div className="route-stat-box">
//                                             <div className="route-stat-value">
//                                                 {optimalRoute?.distance || 'N/A'}
//                                             </div>
//                                             <div className="route-stat-label">Distance</div>
//                                         </div>
//                                         <div className="route-stat-box">
//                                             <div className="route-stat-value">
//                                                 {optimalRoute?.duration ? formatDuration(optimalRoute.duration) : 'N/A'}
//                                             </div>
//                                             <div className="route-stat-label">Duration</div>
//                                         </div>
//                                     </div>

//                                     {/* Total Stops */}
//                                     <div className="route-stats" style={{ marginTop: '12px' }}>
//                                         <div className="route-stat-box">
//                                             <div className="route-stat-value">
//                                                 {2 + (route.intermediates?.length || 0)}
//                                             </div>
//                                             <div className="route-stat-label">Total Stops</div>
//                                         </div>
//                                         <div className="route-stat-box">
//                                             <div className="route-stat-value">
//                                                 {routeCost ? `₹${routeCost}` : '₹--.--'}
//                                             </div>
//                                             <div className="route-stat-label">Cost of Route</div>
//                                         </div>
//                                     </div>
//                                 </div>
//                             </div>
//                         </Popup>
//                     </Polyline>
//                 );
//             })}
//         </>
//     );
// };

import React, { useEffect } from 'react';
import { Polyline, Popup, useMap } from 'react-leaflet';
import { useAppStore } from '../../store/appStore';
import { formatDuration } from '../../utils/formatDuration';
import { generateArcPath } from '../../utils/generateArcPath';
import { decodePolyline } from '../../utils/decodePolyline';
import L from 'leaflet';
import './RoutesLayer.css';


export const RoutesLayer = () => {
    const activeRoutes = useAppStore(state => state.activeRoutes);
    const lastCreatedRouteId = useAppStore(state => state.lastCreatedRouteId);
    const setLastCreatedRouteId = useAppStore(state => state.setLastCreatedRouteId);
    const highlightedRouteIds = useAppStore(state => state.highlightedRouteIds);
    const routes = Object.values(activeRoutes);
    const map = useMap();
    // console.log('RoutesLayer - routes:', routes);
    // console.log('RoutesLayer - activeRoutes:', activeRoutes);

    // Auto-zoom when routes change
    // useEffect(() => {
    //     if (routes.length > 0) {
    //         const bounds = L.latLngBounds([]);
    //         let hasValidBounds = false;

    //         routes.forEach(route => {
    //             // Handle regular routes
    //             const pathData = route.routeData?.optimal_routes?.[0]?.path;
    //             if (pathData) {
    //                 pathData.forEach((p: any) => {
    //                     bounds.extend([p.lat, p.lng]);
    //                     hasValidBounds = true;
    //                 });
    //             }

    //             // Handle multimodal routes
    //             if (route.routeData?.multimodal && route.routeData?.segments) {
    //                 const segments = route.routeData.segments;

    //                 // Segment 1 path
    //                 segments.segment_1?.path?.forEach((p: any) => {
    //                     bounds.extend([p.lat, p.lng]);
    //                     hasValidBounds = true;
    //                 });

    //                 // Segment 2 airports
    //                 if (segments.segment_2?.source_airport) {
    //                     bounds.extend([segments.segment_2.source_airport.lat, segments.segment_2.source_airport.lng]);
    //                     hasValidBounds = true;
    //                 }
    //                 if (segments.segment_2?.destination_airport) {
    //                     bounds.extend([segments.segment_2.destination_airport.lat, segments.segment_2.destination_airport.lng]);
    //                     hasValidBounds = true;
    //                 }

    //                 // Segment 3 path
    //                 segments.segment_3?.path?.forEach((p: any) => {
    //                     bounds.extend([p.lat, p.lng]);
    //                     hasValidBounds = true;
    //                 });
    //             }
    //         });

    //         if (hasValidBounds) {
    //             map.fitBounds(bounds, { padding: [50, 50] });
    //         }
    //     }
    // }, [routes, map]);

    // Auto-zoom to the LATEST route only
    // useEffect(() => {
    //     if (routes.length > 0) {
    //         // 1. Find the latest route by sorting by creation date (descending)
    //         // (We create a copy with [...routes] to avoid mutating the original array)
    //         const latestRoute = [...routes].sort((a, b) =>
    //             new Date(b.created).getTime() - new Date(a.created).getTime()
    //         )[0];

    //         if (!latestRoute) return;

    //         const bounds = L.latLngBounds([]);
    //         let hasValidBounds = false;

    //         // 2. Calculate bounds ONLY for the latestRoute

    //         // Handle regular routes
    //         const pathData = latestRoute.routeData?.optimal_routes?.[0]?.path;
    //         if (pathData) {
    //             pathData.forEach((p: any) => {
    //                 bounds.extend([p.lat, p.lng]);
    //                 hasValidBounds = true;
    //             });
    //         }

    //         // Handle multimodal routes
    //         if (latestRoute.routeData?.multimodal && latestRoute.routeData?.segments) {
    //             const segments = latestRoute.routeData.segments;

    //             // Segment 1 path
    //             segments.segment_1?.path?.forEach((p: any) => {
    //                 bounds.extend([p.lat, p.lng]);
    //                 hasValidBounds = true;
    //             });

    //             // Segment 2 airports
    //             if (segments.segment_2?.source_airport) {
    //                 bounds.extend([segments.segment_2.source_airport.lat, segments.segment_2.source_airport.lng]);
    //                 hasValidBounds = true;
    //             }
    //             if (segments.segment_2?.destination_airport) {
    //                 bounds.extend([segments.segment_2.destination_airport.lat, segments.segment_2.destination_airport.lng]);
    //                 hasValidBounds = true;
    //             }

    //             // Segment 3 path
    //             segments.segment_3?.path?.forEach((p: any) => {
    //                 bounds.extend([p.lat, p.lng]);
    //                 hasValidBounds = true;
    //             });
    //         }

    //         // 3. Fit bounds to just this route
    //         if (hasValidBounds) {
    //             map.fitBounds(bounds, { padding: [50, 50] });
    //         }
    //     }
    // }, [routes, map]);

    // Auto-zoom ONLY when lastCreatedRouteId changes (i.e., a new route was just created)
    useEffect(() => {
        if (lastCreatedRouteId === null) return;

        const latestRoute = activeRoutes[lastCreatedRouteId];
        if (!latestRoute) return;

        const bounds = L.latLngBounds([]);
        let hasValidBounds = false;

        // Handle regular routes
        const rawPath = latestRoute.routeData?.optimal_routes?.[0]?.path;
        if (rawPath) {
            const pathPoints = typeof rawPath === 'string' ? decodePolyline(rawPath) : rawPath;
            pathPoints.forEach((p: any) => {
                bounds.extend([p.lat, p.lng]);
                hasValidBounds = true;
            });
        }

        // Handle multimodal routes
        if (latestRoute.routeData?.multimodal && latestRoute.routeData?.segments) {
            const segments = latestRoute.routeData.segments;

            const seg1Path = segments.segment_1?.path;
            if (seg1Path) {
                const seg1Points = typeof seg1Path === 'string' ? decodePolyline(seg1Path) : seg1Path;
                seg1Points.forEach((p: any) => {
                    bounds.extend([p.lat, p.lng]);
                    hasValidBounds = true;
                });
            }

            if (segments.segment_2?.source_airport) {
                bounds.extend([segments.segment_2.source_airport.lat, segments.segment_2.source_airport.lng]);
                hasValidBounds = true;
            }
            if (segments.segment_2?.destination_airport) {
                bounds.extend([segments.segment_2.destination_airport.lat, segments.segment_2.destination_airport.lng]);
                hasValidBounds = true;
            }

            const seg3Path = segments.segment_3?.path;
            if (seg3Path) {
                const seg3Points = typeof seg3Path === 'string' ? decodePolyline(seg3Path) : seg3Path;
                seg3Points.forEach((p: any) => {
                    bounds.extend([p.lat, p.lng]);
                    hasValidBounds = true;
                });
            }
        }

        if (hasValidBounds) {
            map.fitBounds(bounds, { padding: [50, 50], animate: true });
        }

        // Clear the trigger
        setLastCreatedRouteId(null);

    }, [lastCreatedRouteId, activeRoutes, map, setLastCreatedRouteId]);

    // Render a regular (non-multimodal) route
    const renderRegularRoute = (route: any) => {
        // NEW CODE: Handle both polyline string and lat/lng array
        const rawPath = route.routeData?.optimal_routes?.[0]?.path;
        if (!rawPath) return null;

        let positions: [number, number][];
        if (typeof rawPath === 'string') {
            // Decode polyline string
            const decoded = decodePolyline(rawPath);
            positions = decoded.map(p => [p.lat, p.lng] as [number, number]);
        } else {
            // Legacy: array of {lat, lng} objects
            positions = rawPath.map((p: any) => [p.lat, p.lng] as [number, number]);
        }
        const optimalRoute = route.routeData?.optimal_routes?.[0];
        const routeCost = route.routeData?.route_cost;

        // Determine route color based on cached field
        const getRouteColor = () => {
            if (highlightedRouteIds.length > 0 && highlightedRouteIds.includes(route.id)) return '#FFD700'; // Yellow highlight
            if (route.isActive === false) return '#dc3545';           // Red for inactive
            if (route.routeData?.cached === true) return '#8b5cf6';  // Purple for cached (existing network route highlighted)
            if (route.routeData?.cached === false) return '#f59e0b'; // Orange for uncached (new route, not in network)
            return '#28a745';                                         // Green for normal land route (CSV upload)
        };

        return (
            <Polyline
                key={route.id}
                positions={positions}
                pathOptions={{
                    color: getRouteColor(),
                    // weight: route.isActive === false ? 4 : 5,
                    weight: (highlightedRouteIds.length > 0 && highlightedRouteIds.includes(route.id)) ? 7 : (route.isActive === false ? 4 : 5),
                    opacity: route.isActive === false ? 0.6 : 0.8
                }
                }
            >
                <Popup>
                    <div className="route-popup">
                        <div className="route-popup-header">
                            <h4>Route {route.id}</h4>
                        </div>
                        <div className="route-popup-body">
                            <div className="route-popup-section">
                                <div className="route-popup-label">Type:</div>
                                <span className="route-type-badge">
                                    {route.routeData?.optimal_routes?.[0]?.isOptimal === false
                                        ? 'Alternative Route'
                                        : route.intermediates?.length > 0
                                            ? 'Multi-stop Route'
                                            : 'Optimal Route'}
                                </span>
                            </div>
                            <div className="route-popup-section">
                                <div className="route-popup-label">Route Path:</div>
                                <div className="route-path">
                                    <div className="route-path-item">
                                        <span className="route-path-dot start"></span>
                                        Start: {route.source}
                                    </div>
                                    <span className="route-path-arrow">→</span>
                                    <div className="route-path-item">
                                        <span className="route-path-dot end"></span>
                                        End: {route.destination}
                                    </div>
                                </div>
                            </div>
                            <div className="route-stats">
                                <div className="route-stat-box">
                                    <div className="route-stat-value">
                                        {optimalRoute?.distance || 'N/A'}
                                    </div>
                                    <div className="route-stat-label">Distance</div>
                                </div>
                                <div className="route-stat-box">
                                    <div className="route-stat-value">
                                        {optimalRoute?.duration ? formatDuration(optimalRoute.duration) : 'N/A'}
                                    </div>
                                    <div className="route-stat-label">Duration</div>
                                </div>
                            </div>
                            <div className="route-stats" style={{ marginTop: '12px' }}>
                                <div className="route-stat-box">
                                    <div className="route-stat-value">
                                        {2 + (route.intermediates?.length || 0)}
                                    </div>
                                    <div className="route-stat-label">Total Stops</div>
                                </div>
                                <div className="route-stat-box">
                                    <div className="route-stat-value">
                                        {routeCost ? `₹${routeCost}` : '$--.--'}
                                    </div>
                                    <div className="route-stat-label">Cost of Route</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </Popup>
            </Polyline >
        );
    };

    // Render a multimodal route (road + air + road)
    const renderMultimodalRoute = (route: any) => {
        const segments = route.routeData?.segments;
        if (!segments) return null;

        //const elements: JSX.Element[] = [];
        const elements: React.ReactNode[] = [];

        // Determine colors based on cached field
        const isCachedTrue = route.routeData?.cached === true;
        const isCachedFalse = route.routeData?.cached === false;
        const isInactive = route.isActive === false;

        let roadColor = '#28a745';   // Default green for land segments
        let flightColor = '#72aee6'; // Default blue for air segments

        if (isInactive) {
            roadColor = '#dc3545';    // Red for inactive
            flightColor = '#dc3545';
        } else if (highlightedRouteIds.length > 0 && highlightedRouteIds.includes(route.id)) {
            roadColor = '#FFD700';   // Yellow highlight
            flightColor = '#FFD700';
        } else if (isCachedTrue) {
            roadColor = '#8b5cf6';    // Purple for cached (existing network route highlighted)
            flightColor = '#8b5cf6';
        } else if (isCachedFalse) {
            roadColor = '#f59e0b';    // Orange for uncached (new route, not in network)
            flightColor = '#f59e0b';
        }

        // Unified popup JSX — matches regular route popup exactly
        const unifiedPopup = (
            <Popup>
                <div className="route-popup">
                    <div className="route-popup-header">
                        <h4>Route {route.id}</h4>
                    </div>
                    <div className="route-popup-body">
                        <div className="route-popup-section">
                            <div className="route-popup-label">Type:</div>
                            <span className="route-type-badge">Multimodal Route</span>
                        </div>
                        <div className="route-popup-section">
                            <div className="route-popup-label">Route Path:</div>
                            <div className="route-path">
                                <div className="route-path-item">
                                    <span className="route-path-dot start"></span>
                                    Start: {route.source}
                                </div>
                                <span className="route-path-arrow">→</span>
                                <div className="route-path-item">
                                    <span className="route-path-dot end"></span>
                                    End: {route.destination}
                                </div>
                            </div>
                        </div>
                        <div className="route-stats">
                            <div className="route-stat-box">
                                <div className="route-stat-value">
                                    {route.routeData?.total_distance ? `${route.routeData.total_distance} km` : 'N/A'}
                                </div>
                                <div className="route-stat-label">Distance</div>
                            </div>
                            <div className="route-stat-box">
                                <div className="route-stat-value">
                                    {route.routeData?.total_duration ? formatDuration(route.routeData.total_duration) : 'N/A'}
                                </div>
                                <div className="route-stat-label">Duration</div>
                            </div>
                        </div>
                        <div className="route-stats" style={{ marginTop: '12px' }}>
                            <div className="route-stat-box">
                                <div className="route-stat-value">3</div>
                                <div className="route-stat-label">Total Stops</div>
                            </div>
                            <div className="route-stat-box">
                                <div className="route-stat-value">
                                    {route.routeData?.route_cost ? `₹${route.routeData.route_cost}` : '$--.--'}
                                </div>
                                <div className="route-stat-label">Cost of Route</div>
                            </div>
                        </div>
                    </div>
                </div>
            </Popup>
        );

        // Segment 1: Road to airport (solid line)
        if (segments.segment_1?.path) {
            const seg1Path = segments.segment_1.path;
            const segment1Positions = typeof seg1Path === 'string'
                ? decodePolyline(seg1Path).map(p => [p.lat, p.lng] as [number, number])
                : seg1Path.map((p: any) => [p.lat, p.lng] as [number, number]);
            elements.push(
                <Polyline
                    key={`${route.id}-segment1`}
                    positions={segment1Positions}
                    pathOptions={{ color: roadColor, weight: 5, opacity: 0.8 }}
                >
                    {unifiedPopup}
                </Polyline>
            );
        }

        // Segment 2: Air route (dotted curved line)
        if (segments.segment_2?.source_airport && segments.segment_2?.destination_airport) {
            const airPath = generateArcPath(
                segments.segment_2.source_airport,
                segments.segment_2.destination_airport,
                50
            );
            const airPositions = airPath.map(p => [p.lat, p.lng] as [number, number]);
            elements.push(
                <Polyline
                    key={`${route.id}-segment2`}
                    positions={airPositions}
                    pathOptions={{ color: flightColor, weight: 4, opacity: 0.9, dashArray: '10, 10', lineCap: 'round' }}
                >
                    {unifiedPopup}
                </Polyline>
            );
        }

        // Segment 3: Road from airport to destination (solid line)
        if (segments.segment_3?.path) {
            const seg3Path = segments.segment_3.path;
            const segment3Positions = typeof seg3Path === 'string'
                ? decodePolyline(seg3Path).map(p => [p.lat, p.lng] as [number, number])
                : seg3Path.map((p: any) => [p.lat, p.lng] as [number, number]);
            elements.push(
                <Polyline
                    key={`${route.id}-segment3`}
                    positions={segment3Positions}
                    pathOptions={{ color: roadColor, weight: 5, opacity: 0.8 }}
                >
                    {unifiedPopup}
                </Polyline>
            );
        }

        return <React.Fragment key={route.id}>{elements}</React.Fragment>;
    };

    return (
        <>
            {routes.map((route) => {
                // Check if it's a multimodal route
                if (route.routeData?.multimodal && route.routeData?.segments) {
                    return renderMultimodalRoute(route);
                }
                // Regular route
                return renderRegularRoute(route);
            })}
        </>
    );
};