import { useState } from 'react';
import { routesApi } from '../api/routes';
import type { RouteUploadEntry } from '../api/routes';
import { useAppStore } from '../store/appStore';
import './RouteUploadTable.css';

interface RouteRow {
    source: string;
    destination: string;
    intermediate: string;
    type: 'road' | 'air';
    // objective: 'cost' | 'duration' | 'distance';
}

const emptyRow = (): RouteRow => ({
    source: '',
    destination: '',
    intermediate: '',
    type: 'road',
    // objective: 'duration',
});

interface RouteUploadTableProps {
    isOpen: boolean;
    onClose: () => void;
}

export const RouteUploadTable = ({ isOpen, onClose }: RouteUploadTableProps) => {
    const [rows, setRows] = useState<RouteRow[]>([emptyRow()]);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadResult, setUploadResult] = useState<string | null>(null);

    const { setActiveRoutes, addChatMessage } = useAppStore();

    const updateRow = (index: number, field: keyof RouteRow, value: string) => {
        setRows(prev => {
            const updated = [...prev];
            updated[index] = { ...updated[index], [field]: value };
            return updated;
        });
    };

    const addRow = () => {
        setRows(prev => [...prev, emptyRow()]);
    };

    const removeRow = (index: number) => {
        if (rows.length <= 1) return;
        setRows(prev => prev.filter((_, i) => i !== index));
    };

    // const handleUpload = async () => {
    //     // Validate: at least one row with source + destination
    //     const validRows = rows.filter(r => r.source.trim() && r.destination.trim());
    //     if (validRows.length === 0) {
    //         setUploadResult('❌ Please fill in at least one route with source and destination.');
    //         return;
    //     }

    //     setIsUploading(true);
    //     setUploadResult(null);

    //     try {
    //         // Build the payload
    //         const routes: RouteUploadEntry[] = validRows.map(row => ({
    //             source: row.source.trim(),
    //             destination: row.destination.trim(),
    //             intermediate: row.intermediate
    //                 .split(',')
    //                 .map(s => s.trim())
    //                 .filter(s => s.length > 0),
    //             type: row.type,
    //             objective: row.objective,
    //         }));

    //         const response = await routesApi.uploadRoutesJson(routes);

    //         if (response.success) {
    //             // Map the response into activeRoutes — same logic as CSV upload in ChatPanel
    //             const allRoutes: Record<number, any> = {};
    //             const routeData = response.data;

    //             // 1. Map road routes
    //             if (routeData?.road_routes) {
    //                 routeData.road_routes.forEach((route: any) => {
    //                     allRoutes[route.route_id] = {
    //                         id: route.route_id,
    //                         source: route.source,
    //                         destination: route.destination,
    //                         intermediates: route.intermediate_locations || [],
    //                         waypoints: route.locations || [route.source, route.destination],
    //                         created: new Date(),
    //                         isActive: true,
    //                         routeData: {
    //                             route_id: route.route_id,
    //                             source: route.source,
    //                             destination: route.destination,
    //                             optimal_routes: route.optimal_routes,
    //                             route_cost: route.route_cost ? Number(route.route_cost).toFixed(2) : null,
    //                             source_coords: route.source_coords,
    //                             dest_coords: route.dest_coords,
    //                             distance: route.distance,
    //                             duration: route.duration,
    //                         },
    //                     };
    //                 });
    //             }

    //             // 2. Map multimodal routes
    //             if (routeData?.multimodal_routes) {
    //                 routeData.multimodal_routes.forEach((route: any) => {
    //                     const multimodalData = route.data;
    //                     allRoutes[route.route_id] = {
    //                         id: route.route_id,
    //                         source: multimodalData.source,
    //                         destination: multimodalData.destination,
    //                         intermediates: [],
    //                         waypoints: [multimodalData.source, multimodalData.destination],
    //                         created: new Date(),
    //                         isActive: true,
    //                         isMultimodal: true,
    //                         routeData: {
    //                             route_id: route.route_id,
    //                             source: route.source,
    //                             destination: route.destination,
    //                             multimodal: true,
    //                             segments: {
    //                                 segment_1: multimodalData?.segment_1,
    //                                 segment_2: multimodalData?.segment_2,
    //                                 segment_3: multimodalData?.segment_3,
    //                             },
    //                             total_distance: multimodalData?.total_distance_km,
    //                             total_duration: multimodalData?.total_duration,
    //                             route_cost: (
    //                                 (multimodalData?.segment_1?.route_cost || 0) +
    //                                 (multimodalData?.segment_3?.route_cost || 0)
    //                             ).toFixed(2),
    //                         },
    //                     };
    //                 });
    //             }

    //             // 3. Merge with existing routes (don't overwrite)
    //             const { activeRoutes } = useAppStore.getState();
    //             setActiveRoutes({ ...activeRoutes, ...allRoutes });

    //             const roadCount = routeData?.road_routes?.length || 0;
    //             const multimodalCount = routeData?.multimodal_routes?.length || 0;

    //             const successMsg = `✅ ${response.message} (${roadCount} road routes, ${multimodalCount} multimodal routes loaded)`;
    //             setUploadResult(successMsg);
    //             addChatMessage('assistant', successMsg);

    //             // Reset table after success
    //             setRows([emptyRow()]);
    //         } else {
    //             setUploadResult(`❌ Upload failed: ${response.message}`);
    //         }
    //     } catch (error: any) {
    //         const errMsg = error.response?.data?.detail || error.response?.data?.message || error.message;
    //         setUploadResult(`❌ Failed to upload routes: ${errMsg}`);
    //     } finally {
    //         setIsUploading(false);
    //     }
    // };

    const handleUpload = async () => {
        // Validate: at least one row with source + destination
        const validRows = rows.filter(r => r.source.trim() && r.destination.trim());
        if (validRows.length === 0) {
            setUploadResult('❌ Please fill in at least one route with source and destination.');
            return;
        }

        setIsUploading(true);
        setUploadResult(null);

        try {
            // Build the payload
            const routes: RouteUploadEntry[] = validRows.map(row => ({
                source: row.source.trim(),
                destination: row.destination.trim(),
                intermediate: row.intermediate
                    .split(',')
                    .map(s => s.trim())
                    .filter(s => s.length > 0),
                type: row.type,
                // objective: row.objective,
            }));

            const response = await routesApi.uploadRoutesJson(routes);

            if (response.success) {
                // Map the response into activeRoutes — same logic as CSV upload in ChatPanel
                const allRoutes: Record<number, any> = {};
                const routeData = response.data;

                // 1. Map road routes
                if (routeData?.road_routes) {
                    routeData.road_routes.forEach((route: any) => {
                        allRoutes[route.route_id] = {
                            id: route.route_id,
                            source: route.source,
                            destination: route.destination,
                            intermediates: route.intermediate_locations || [],
                            waypoints: route.locations || [route.source, route.destination],
                            created: new Date(),
                            isActive: true,
                            routeData: {
                                route_id: route.route_id,
                                route_type: route.route_type || route.type || 'road',
                                source: route.source,
                                destination: route.destination,
                                optimal_routes: route.optimal_routes,
                                route_cost: route.route_cost ? Number(route.route_cost).toFixed(2) : null,
                                source_coords: route.source_coords,
                                dest_coords: route.dest_coords,
                                distance: route.distance,
                                duration: route.duration,
                            },
                        };
                    });
                }

                // 2. Map multimodal routes
                if (routeData?.multimodal_routes) {
                    routeData.multimodal_routes.forEach((route: any) => {
                        const multimodalData = route.data;
                        allRoutes[route.route_id] = {
                            id: route.route_id,
                            source: multimodalData.source,
                            destination: multimodalData.destination,
                            intermediates: [],
                            waypoints: [multimodalData.source, multimodalData.destination],
                            created: new Date(),
                            isActive: true,
                            isMultimodal: true,
                            routeData: {
                                route_id: route.route_id,
                                source: route.source,
                                destination: route.destination,
                                multimodal: true,
                                segments: {
                                    segment_1: multimodalData?.segment_1,
                                    segment_2: multimodalData?.segment_2,
                                    segment_3: multimodalData?.segment_3,
                                },
                                total_distance: multimodalData?.total_distance_km,
                                total_duration: multimodalData?.total_duration,
                                route_cost: (multimodalData?.total_cost ?? route.total_cost)?.toFixed?.(2) ??
                                    Number(multimodalData?.total_cost ?? route.total_cost).toFixed(2),
                            },
                        };
                    });
                }

                // 3. Map air intermediate routes
                if (routeData?.air_intermediate_route) {
                    routeData.air_intermediate_route.forEach((group: any) => {
                        if (!group.status || !group.routes) return;

                        group.routes.forEach((leg: any) => {
                            const routeId = leg.route_id || Date.now();
                            const legData = leg.data || leg;

                            allRoutes[routeId] = {
                                id: routeId,
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
                                    total_distance: legData.total_distance_km,
                                    objective: legData.objective || legData.segment_1?.objective || null,
                                    //cached: leg.cached !== undefined ? leg.cached : undefined,
                                },
                            };
                        });
                    });
                }

                // 4. Merge with existing routes (don't overwrite)
                const { activeRoutes } = useAppStore.getState();
                setActiveRoutes({ ...activeRoutes, ...allRoutes });

                const roadCount = routeData?.road_routes?.length || 0;
                const multimodalCount = routeData?.multimodal_routes?.length || 0;
                const airIntermediateCount = routeData?.air_intermediate_route?.reduce(
                    (acc: number, group: any) => acc + (group.routes?.length || 0), 0
                ) || 0;

                const successMsg = `✅ ${response.message} (${roadCount} road, ${multimodalCount} multimodal, ${airIntermediateCount} air intermediate routes loaded)`;
                setUploadResult(successMsg);
                addChatMessage('assistant', successMsg);

                // Reset table after success
                setRows([emptyRow()]);

                setTimeout(() => {
                    setUploadResult(null);
                    onClose();
                }, 2000);


            } else {
                setUploadResult(`❌ Upload failed: ${response.message}`);
            }
        } catch (error: any) {
            const errMsg = error.response?.data?.detail || error.response?.data?.message || error.message;
            setUploadResult(`❌ Failed to upload routes: ${errMsg}`);
        } finally {
            setIsUploading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="route-upload-overlay" onClick={onClose}>
            <div className="route-upload-modal" onClick={e => e.stopPropagation()}>
                <div className="route-upload-header">
                    <h3>📋 Upload Routes</h3>
                    <button className="route-upload-close" onClick={onClose}>✕</button>
                </div>

                <div className="route-upload-body">
                    <div className="route-upload-table-wrapper">
                        <table className="route-upload-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Source</th>
                                    <th>Destination</th>
                                    <th>Intermediate (comma-separated)</th>
                                    <th>Type</th>
                                    {/* <th>Objective</th> */}
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((row, idx) => (
                                    <tr key={idx}>
                                        <td className="row-num">{idx + 1}</td>
                                        <td>
                                            <input
                                                type="text"
                                                value={row.source}
                                                onChange={e => updateRow(idx, 'source', e.target.value)}
                                                placeholder="Source Warehouse Name"
                                            />
                                        </td>
                                        <td>
                                            <input
                                                type="text"
                                                value={row.destination}
                                                onChange={e => updateRow(idx, 'destination', e.target.value)}
                                                placeholder="Destination Warehouse Name"
                                            />
                                        </td>
                                        <td>
                                            <input
                                                type="text"
                                                value={row.intermediate}
                                                onChange={e => updateRow(idx, 'intermediate', e.target.value)}
                                                placeholder="Intermediates (comma-separated)"
                                            />
                                        </td>
                                        <td>
                                            <select
                                                value={row.type}
                                                onChange={e => updateRow(idx, 'type', e.target.value)}
                                            >
                                                <option value="road">Road</option>
                                                <option value="air">Air</option>
                                            </select>
                                        </td>
                                        {/* <td>
                                            <select
                                                value={row.objective}
                                                onChange={e => updateRow(idx, 'objective', e.target.value)}
                                            >
                                                <option value="cost">Cost</option>
                                                <option value="duration">Duration</option>
                                                <option value="distance">Distance</option>
                                            </select>
                                        </td> */}
                                        <td>
                                            <button
                                                className="remove-row-btn"
                                                onClick={() => removeRow(idx)}
                                                disabled={rows.length <= 1}
                                                title="Remove row"
                                            >
                                                🗑️
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <div className="route-upload-actions">
                        <button className="add-row-btn" onClick={addRow}>
                            + Add Row
                        </button>
                        <button
                            className="upload-btn"
                            onClick={handleUpload}
                            disabled={isUploading}
                        >
                            {isUploading ? '⏳ Uploading...' : '📤 Upload Routes'}
                        </button>
                    </div>

                    {uploadResult && (
                        <div className={`upload-result ${uploadResult.startsWith('✅') ? 'success' : 'error'}`}>
                            {uploadResult}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
