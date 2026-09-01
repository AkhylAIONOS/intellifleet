import { useAppStore } from '../store/appStore';
import './VehicleInfoDashboard.css';

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

// Helper function to get status color
const getStatusColor = (status: string): string => {
    switch (status?.toLowerCase()) {
        case 'available':
            return '#28a745'; // green
        case 'assigned':
            return '#dc3545'; // red
        case 'completed':
            return '#ff8c00'; // orange
        case 'disrupted':
            return '#6c757d'; // gray 
        default:
            return '#333333'; // default
    }
};

export const VehicleInfoDashboard = () => {
    const { vehicles, activeDashboard, setActiveDashboard } = useAppStore();
    const isOpen = activeDashboard === 'vehicleInfo';

    const toggleDashboard = () => {
        setActiveDashboard(isOpen ? null : 'vehicleInfo');
    };



    // Download function - exports table as CSV
    const handleDownload = () => {
        const headers = ['Vehicle ID', 'Vehicle Type', 'Capacity', 'Initial Warehouse', 'Current Location', 'Status', 'Scheduled Departure'];

        const rows = vehicles.map(vehicle => {
            return [
                vehicle.id,
                vehicle.type,
                vehicle.capacity ?? 'N/A',
                vehicle.warehouse_name,
                vehicle.current_location || 'N/A',
                vehicle.status || 'NA',
                vehicle.schedule_departure_time || 'Not Scheduled'
            ].join(',');
        });

        const csvContent = '\uFEFF' + [headers.join(','), ...rows].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `vehicles_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    // Minimized View (Button)
    if (!isOpen) {
        return (
            <div className="vehicle-info-trigger-container">
                <button className="vehicle-info-trigger-btn" onClick={toggleDashboard}>
                    <span className="trigger-icon">🚛</span>
                    <span className="trigger-text">Vehicles</span>
                    {vehicles.length > 0 && (
                        <span className="trigger-badge">{vehicles.length}</span>
                    )}
                </button>
            </div>
        );
    }

    // Expanded View (Table)
    return (
        <div className="vehicle-info-dashboard">
            <div className="dashboard-header">
                <h3>Vehicle Information</h3>
                <div className="header-actions">
                    <button
                        className="download-btn"
                        onClick={handleDownload}
                        title="Download as CSV"
                        disabled={vehicles.length === 0}
                    >
                        ⬇️
                    </button>
                    <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
                </div>
            </div>

            {vehicles.length === 0 ? (
                <div className="empty-state">
                    <p>No vehicles available</p>
                </div>
            ) : (
                <div className="table-container">
                    <table className="vehicles-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Type</th>
                                <th>Capacity(kg)</th>
                                <th>Initial Warehouse</th>
                                <th>Current Location</th>
                                <th>Status</th>
                                <th>Scheduled <br></br>Departure</th>
                            </tr>
                        </thead>
                        <tbody>
                            {vehicles.map(vehicle => (
                                <tr key={vehicle.id}>
                                    <td>{vehicle.id}</td>
                                    <td style={{ textTransform: 'capitalize', color: getVehicleTypeColor(vehicle.type), fontWeight: '600' }}>{vehicle.type}</td>
                                    <td>{vehicle.capacity ?? 'N/A'}</td>
                                    <td>{vehicle.warehouse_name}</td>
                                    <td>{vehicle.current_location || 'N/A'}</td>
                                    <td style={{ textTransform: 'capitalize', color: getStatusColor(vehicle.status), fontWeight: '600' }}>{vehicle.status || 'NA'}</td>
                                    <td style={{ color: '#1976d2', fontWeight: '600' }}>{vehicle.schedule_departure_time || 'Not Scheduled'}</td>
                                </tr>
                            ))}
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