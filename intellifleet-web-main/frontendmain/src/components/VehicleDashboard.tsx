// import { useState, useEffect } from 'react';
// import { useAppStore } from '../store/appStore';
// import './VehicleDashboard.css';

// export const VehicleDashboard = () => {
//     const { vehicles } = useAppStore();
//     const [isOpen, setIsOpen] = useState(false);
//     const [currentIndex, setCurrentIndex] = useState(0);

//     // Only show assigned vehicles
//     const activeVehicles = vehicles.filter(v => v.status === 'assigned' && v.assigned_route);
//     const hasVehicles = activeVehicles.length > 0;

//     // Reset currentIndex when active vehicles change
//     useEffect(() => {
//         if (currentIndex >= activeVehicles.length && activeVehicles.length > 0) {
//             setCurrentIndex(activeVehicles.length - 1);
//         } else if (activeVehicles.length === 0) {
//             setCurrentIndex(0);
//         }
//     }, [activeVehicles.length, currentIndex]);

//     const handleToggle = () => setIsOpen(!isOpen);

//     const handleNext = () => {
//         if (currentIndex < activeVehicles.length - 1) {
//             setCurrentIndex(prev => prev + 1);
//         }
//     };

//     const handlePrev = () => {
//         if (currentIndex > 0) {
//             setCurrentIndex(prev => prev - 1);
//         }
//     };

//     const currentVehicle = hasVehicles ? activeVehicles[currentIndex] : null;

//     // Calculate progress (mock - in real app would be based on actual distance traveled)
//     // const getProgress = (vehicle: any) => {
//     //     return vehicle.assigned_route?.progress || 0;
//     // };

//     return (
//         <>
//             <button
//                 className="dashboard-toggle"
//                 onClick={handleToggle}
//                 title={isOpen ? "Close Dashboard" : "Show Vehicle Dashboard"}
//             >
//                 <span className="trigger-icon">🚗</span>
//                 <span className="trigger-text"> Active Vehicles</span>
//             </button>

//             <div className={`vehicle-dashboard ${isOpen ? 'open' : ''}`}>
//                 <div className="dashboard-header">
//                     <h3>Active Vehicles</h3>
//                     <div className="vehicle-count">{activeVehicles.length}</div>
//                 </div>

//                 <div className="dashboard-content">
//                     {!hasVehicles ? (
//                         <div className="no-vehicles">
//                             <div className="no-vehicles-icon">🚗</div>
//                             <p className="no-vehicles-title">No active vehicles</p>
//                             <small className="no-vehicles-subtitle">Assign vehicles to routes to see them here</small>
//                         </div>
//                     ) : (
//                         currentVehicle && (
//                             <div className="vehicle-card">
//                                 <div className="vehicle-card-header">
//                                     <span className="vehicle-name">{currentVehicle.id}</span>
//                                     <span className="vehicle-type-badge">{currentVehicle.type}</span>
//                                 </div>

//                                 {currentVehicle.assigned_route && (
//                                     <div className="vehicle-route-status">
//                                         In Transit - {currentVehicle.assigned_route.source} → {currentVehicle.assigned_route.destination}
//                                     </div>
//                                 )}

//                                 {/* <div className="progress-section">
//                                     <div className="progress-label">Progress</div>
//                                     <div className="progress-value">{getProgress(currentVehicle)}%</div>
//                                 </div>
//                                 <div className="progress-bar">
//                                     <div
//                                         className="progress-fill"
//                                         style={{ width: `${getProgress(currentVehicle)}%` }}
//                                     ></div>
//                                 </div> */}

//                                 <div className="vehicle-stats">
//                                     <div className="stat-row">
//                                         <span className="stat-label">Vehicle Type:</span>
//                                         <span className="stat-value">{currentVehicle.type}</span>
//                                     </div>
//                                     <div className="stat-row">
//                                         <span className="stat-label">Capacity:</span>
//                                         <span className="stat-value">
//                                             {currentVehicle.assigned_route?.vehicle_details?.capacity || 'N/A'}
//                                         </span>
//                                     </div>
//                                     <div className="stat-row">
//                                         <span className="stat-label">Speed:</span>
//                                         <span className="stat-value">
//                                             {currentVehicle.assigned_route?.vehicle_details?.speed
//                                                 ? `${currentVehicle.assigned_route.vehicle_details.speed} km/h`
//                                                 : 'N/A'}
//                                         </span>
//                                     </div>
//                                     <div className="stat-row">
//                                         <span className="stat-label">Fuel Type:</span>
//                                         <span className="stat-value">
//                                             {currentVehicle.assigned_route?.vehicle_details?.fuel_type || 'N/A'}
//                                         </span>
//                                     </div>
//                                     <div className="stat-row">
//                                         <span className="stat-label">Mileage:</span>
//                                         <span className="stat-value">
//                                             {currentVehicle.assigned_route?.vehicle_details?.fuel_consumption
//                                                 ? `${currentVehicle.assigned_route.vehicle_details.fuel_consumption} km/L`
//                                                 : 'N/A'}
//                                         </span>
//                                     </div>
//                                 </div>
//                             </div>
//                         )
//                     )}
//                 </div>

//                 <div className="dashboard-controls">
//                     <div className="nav-buttons">
//                         <button
//                             className="nav-btn"
//                             onClick={handlePrev}
//                             disabled={!hasVehicles || currentIndex === 0}
//                         >
//                             Previous
//                         </button>
//                         <button
//                             className="nav-btn"
//                             onClick={handleNext}
//                             disabled={!hasVehicles || currentIndex === activeVehicles.length - 1}
//                         >
//                             Next
//                         </button>
//                     </div>
//                     <button className="close-dashboard" onClick={handleToggle}>Close</button>
//                 </div>
//             </div>
//         </>
//     );
// };

import { useAppStore } from '../store/appStore';
import './VehicleDashboard.css';

// Helper function to get vehicle type color
const getVehicleTypeColor = (type: string): string => {
    switch (type.toLowerCase()) {
        case 'truck':
            return '#654321'; // dark brown
        case 'bike':
            return '#ff8c00'; // orange
        case 'car':
            return '#800020'; // burgundy
        case 'auto':
            return '#b8860b'; // dark yellow
        case 'plane':
            return '#00008b'; // dark blue
        default:
            return '#333333'; // default dark gray
    }
};

export const VehicleDashboard = () => {
    const { vehicles, activeDashboard, setActiveDashboard } = useAppStore();
    const isOpen = activeDashboard === 'vehicleDashboard';

    // Filter only assigned vehicles
    const assignedVehicles = vehicles.filter(v => v.status === 'assigned' && v.assigned_route);

    const toggleDashboard = () => {
        setActiveDashboard(isOpen ? null : 'vehicleDashboard');
    };

    // Download function - exports table as CSV
    const handleDownload = () => {
        const headers = ['ID', 'Type', 'Capacity', 'Source', 'Destination', 'Actual Departure', 'Speed', 'Mileage', 'Fuel'];

        const rows = assignedVehicles.map(vehicle => {
            const details = vehicle.assigned_route?.vehicle_details;
            return [
                vehicle.id,
                vehicle.type,
                vehicle.capacity ?? 'N/A',
                vehicle.assigned_route?.source || 'N/A',
                vehicle.assigned_route?.destination || 'N/A',
                vehicle.departure_time || 'N/A',
                details?.speed ?? 'N/A',
                details?.fuel_consumption ?? 'N/A',
                details?.fuel_type || 'N/A'
            ].join(',');
        });

        const csvContent = '\uFEFF' + [headers.join(','), ...rows].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `assigned_vehicles_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    // Minimized View (Button)
    if (!isOpen) {
        return (
            <button className="dashboard-toggle" onClick={toggleDashboard}>
                <span className="trigger-icon">🚚</span>
                <span className="trigger-text">Assigned Vehicles</span>
                {assignedVehicles.length > 0 && (
                    <span className="trigger-badge">{assignedVehicles.length}</span>
                )}
            </button>
        );
    }

    // Expanded View (Table)
    return (
        <div className="vehicle-dashboard open">
            <div className="dashboard-header">
                <h3>Assigned Vehicles</h3>
                <div className="header-actions">
                    <button
                        className="download-btn"
                        onClick={handleDownload}
                        title="Download as CSV"
                        disabled={assignedVehicles.length === 0}
                    >
                        ⬇️
                    </button>
                    <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
                </div>
            </div>

            {assignedVehicles.length === 0 ? (
                <div className="empty-state">
                    <p>No vehicles currently assigned</p>
                </div>
            ) : (
                <div className="table-container">
                    <table className="assigned-vehicles-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Type</th>
                                <th>Capacity(kg)</th>
                                <th>Source</th>
                                <th>Destination</th>
                                <th>Actual Departure</th>
                                <th>Estimated Arrival</th>
                                <th>Speed(km/h)</th>
                                <th>Mileage(kmpl)</th>
                                <th>Fuel</th>
                            </tr>
                        </thead>
                        <tbody>
                            {assignedVehicles.map(vehicle => {
                                const details = vehicle.vehicle_details;
                                return (
                                    <tr key={vehicle.id}>
                                        <td>{vehicle.id}</td>
                                        <td style={{ textTransform: 'capitalize', color: getVehicleTypeColor(vehicle.type), fontWeight: '600' }}>{vehicle.type}</td>
                                        <td>{vehicle.capacity ?? 'N/A'}</td>
                                        <td style={{ color: '#28a745', fontWeight: '600' }}>{vehicle.assigned_route?.source || 'N/A'}</td>
                                        <td style={{ color: '#dc3545', fontWeight: '600' }}>{vehicle.assigned_route?.destination || 'N/A'}</td>
                                        <td style={{ color: '#28a745', fontWeight: '600' }}>{vehicle.departure_time || 'N/A'}</td>
                                        <td style={{ color: '#dc3545', fontWeight: '600' }}>{vehicle.arrival_time || 'N/A'}</td>
                                        <td>{details?.speed ?? 'N/A'}</td>
                                        <td>{details?.fuel_consumption ?? 'N/A'}</td>
                                        <td>{details?.fuel_type || 'N/A'}</td>
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