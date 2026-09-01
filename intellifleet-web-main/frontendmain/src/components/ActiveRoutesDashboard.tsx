import { useAppStore } from '../store/appStore';
import { formatDuration } from '../utils/formatDuration';
import './ActiveRoutesDashboard.css';

export const ActiveRoutesDashboard = () => {
    const { activeRoutes, activeDashboard, setActiveDashboard } = useAppStore();
    const isOpen = activeDashboard === 'activeRoutes';

    // Filter only ACTIVE routes (isActive !== false)
    const activeRoutesArray = Object.values(activeRoutes).filter(
        route => route.isActive !== false
    );

    const toggleDashboard = () => {
        setActiveDashboard(isOpen ? null : 'activeRoutes');
    };

    // Download function - exports table as CSV
    const handleDownload = () => {
        const headers = ['Route ID', 'Source', 'Destination', 'Distance', 'Duration', 'Cost'];

        const rows = activeRoutesArray.map(route => {
            const isMultimodal = route.routeData?.multimodal === true;
            const optimalRoute = route.routeData?.optimal_routes?.[0];
            const cost = route.routeData?.route_cost;

            const distance = isMultimodal
                ? route.routeData?.total_distance
                : optimalRoute?.distance;
            const duration = isMultimodal
                ? route.routeData?.total_duration
                : optimalRoute?.duration;


            // --- CHANGE 1: Logic for CSV string ---
            let durationString = duration ? formatDuration(duration) : 'N/A';
            if (isMultimodal && duration) {
                durationString += ' + waiting time';
            }

            let costString = cost ? `₹${cost}` : 'N/A';

            // --------------------------------------

            return [
                route.id,
                route.source,
                route.destination,
                distance ? `${distance} km` : 'N/A',
                durationString,
                costString
                //route.routeData?.objective || optimalRoute?.objective || 'N/A'
            ].join(',');
        });

        //const csvContent = [headers.join(','), ...rows].join('\n');
        const csvContent = '\uFEFF' + [headers.join(','), ...rows].join('\n'); // Added BOM
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `active_routes_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    // Minimized View (Button)
    if (!isOpen) {
        return (
            <div className="active-routes-trigger-container">
                <button className="active-routes-trigger-btn" onClick={toggleDashboard}>
                    <span className="trigger-icon">📊</span>
                    <span className="trigger-text">Active Routes</span>
                    {activeRoutesArray.length > 0 && (
                        <span className="trigger-badge">{activeRoutesArray.length}</span>
                    )}
                </button>
            </div>
        );
    }

    // Expanded View (Table)
    return (
        <div className="active-routes-dashboard">
            <div className="dashboard-header">
                <h3>Active Routes</h3>
                <div className="header-actions">
                    <button
                        className="download-btn"
                        onClick={handleDownload}
                        title="Download as CSV"
                        disabled={activeRoutesArray.length === 0}
                    >
                        ⬇️
                    </button>
                    <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
                </div>
            </div>

            {activeRoutesArray.length === 0 ? (
                <div className="empty-state">
                    <p>No active routes</p>
                </div>
            ) : (
                <div className="table-container">
                    <table className="routes-table">
                        <thead>
                            <tr>
                                <th>Route ID</th>
                                <th>Source</th>
                                <th>Destination</th>
                                <th>Distance</th>
                                <th>Duration</th>
                                <th>Cost</th>
                                {/* <th>Objective</th> */}
                            </tr>
                        </thead>
                        <tbody>
                            {activeRoutesArray.map(route => {
                                const isMultimodal = route.routeData?.multimodal === true;
                                const optimalRoute = route.routeData?.optimal_routes?.[0];
                                const cost = route.routeData?.route_cost;

                                // Get distance and duration based on route type
                                const distance = isMultimodal
                                    ? route.routeData?.total_distance
                                    : optimalRoute?.distance;
                                const duration = isMultimodal
                                    ? route.routeData?.total_duration
                                    : optimalRoute?.duration;

                                return (
                                    <tr key={route.id}>
                                        <td>{route.id}</td>
                                        <td style={{ color: '#28a745', fontWeight: '600' }}>{route.source}</td>
                                        <td style={{ color: '#dc3545', fontWeight: '600' }}>{route.destination}</td>
                                        <td>{distance ? `${distance} km` : 'N/A'}</td>
                                        <td>
                                            {duration ? formatDuration(duration) : 'N/A'}
                                            {/* {isMultimodal && duration && (
                                                <span style={{ fontSize: '0.85em', color: '#666', marginLeft: '4px' }}>
                                                    + waiting time
                                                </span>
                                            )} */}
                                        </td>
                                        <td>
                                            {cost ? `₹${cost}` : 'N/A'}

                                        </td>
                                        {/* <td style={{ textTransform: 'capitalize' }}>
                                            {route.routeData?.objective || optimalRoute?.objective || 'N/A'}
                                        </td> */}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* <div className="dashboard-footer">
                <button className="close-button" onClick={toggleDashboard}>Close</button>
            </div> */}
        </div>
    );
};