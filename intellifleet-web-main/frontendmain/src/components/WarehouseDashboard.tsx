// import { useState } from 'react';
// import { useAppStore } from '../store/appStore';
// import './WarehouseDashboard.css';

// export const WarehouseDashboard = () => {
//     const { warehouseInventory, warehouses } = useAppStore();
//     const [isOpen, setIsOpen] = useState(false);

//     const toggleDashboard = () => {
//         setIsOpen(!isOpen);
//     };

//     // Minimized View (Button)
//     if (!isOpen) {
//         return (
//             <div className="warehouse-dashboard-trigger-container">
//                 <button className="warehouse-dashboard-trigger-btn" onClick={toggleDashboard}>
//                     <span className="trigger-icon">🏭</span>
//                     <span className="trigger-text">Warehouses</span>
//                     {warehouseInventory.length > 0 && (
//                         <span className="trigger-badge">{warehouseInventory.length}</span>
//                     )}
//                 </button>
//             </div>
//         );
//     }

//     // Expanded View (Table)
//     return (
//         <div className="warehouse-dashboard">
//             <div className="dashboard-header">
//                 <h3>Warehouse Inventory</h3>
//                 <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
//             </div>

//             {warehouseInventory.length === 0 ? (
//                 <div className="empty-state">
//                     <p>📦 Please upload a CSV file to see all warehouse information</p>
//                 </div>
//             ) : (
//                 <div className="table-container">
//                     <table className="warehouse-table">
//                         <thead>
//                             <tr>
//                                 <th>Warehouse ID</th>
//                                 <th>Warehouse Name</th>
//                                 <th>City</th>
//                                 <th>Country</th>

//                                 <th>Inventory</th>
//                                 <th>Reorder Level</th>
//                             </tr>
//                         </thead>
//                         <tbody>
//                             {warehouseInventory.map((warehouse) => (
//                                 <tr key={warehouse.warehouse_id}>
//                                     <td>{warehouse.warehouse_id}</td>
//                                     <td>{warehouse.warehouse_name}</td>
//                                     <td>
//                                         <span className={warehouse.inventory <= warehouse.reorder_level ? 'low-stock' : ''}>
//                                             {warehouse.inventory}
//                                         </span>
//                                     </td>
//                                     <td>{warehouse.reorder_level}</td>
//                                 </tr>
//                             ))}
//                         </tbody>
//                     </table>
//                 </div>
//             )}

//             <div className="dashboard-footer">
//                 <button className="close-button" onClick={toggleDashboard}>Close</button>
//             </div>
//         </div>
//     );
// };

import { useAppStore } from '../store/appStore';
import './WarehouseDashboard.css';

export const WarehouseDashboard = ({hideTrigger=false}:{hideTrigger?:boolean}) => {
    const { warehouses, activeDashboard, setActiveDashboard } = useAppStore();
    const isOpen = activeDashboard === 'warehouse';

    const toggleDashboard = () => {
        setActiveDashboard(isOpen ? null : 'warehouse');
    };

    // Minimized View (Button)
    if (!isOpen) {
        if(hideTrigger) return null;
        return (
            <div className="warehouse-dashboard-trigger-container">
                <button className="warehouse-dashboard-trigger-btn" onClick={toggleDashboard}>
                    <span className="trigger-icon">🏭</span>
                    <span className="trigger-text">Warehouses</span>
                    {warehouses.length > 0 && (
                        <span className="trigger-badge">{warehouses.length}</span>
                    )}
                </button>
            </div>
        );
    }

    // Expanded View (Table)
    return (
        <div className="warehouse-dashboard">
            <div className="dashboard-header">
                <h3>Warehouse Details</h3>
                <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
            </div>

            {warehouses.length === 0 ? (
                <div className="empty-state">
                    <p>📦 Please upload a CSV file to see all warehouse information</p>
                </div>
            ) : (
                <div className="table-container">
                    <table className="warehouse-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>City</th>
                                <th>Country</th>
                                <th>Node Type</th>
                                <th>Functional</th>
                                <th>Inventory</th>
                                <th>Reorder Level</th>
                            </tr>
                        </thead>
                        <tbody>
                            {warehouses.map((warehouse) => (
                                <tr key={warehouse.id}>
                                    <td>{warehouse.warehouse_id || warehouse.id}</td>
                                    <td>{warehouse.name}</td>
                                    <td>{warehouse.city || 'N/A'}</td>
                                    <td>{warehouse.country || 'N/A'}</td>
                                    <td>{warehouse.node_type || 'N/A'}</td>
                                    <td>
                                        <span style={{
                                            color: warehouse.is_active === 1 ? '#28a745' : '#dc3545',
                                            fontWeight: '600'
                                        }}>
                                            {warehouse.is_active === 1 ? 'Yes' : 'No'}
                                        </span>
                                    </td>
                                    <td>
                                        <span className={
                                            (warehouse.inventory && warehouse.reorder_level &&
                                                warehouse.inventory <= warehouse.reorder_level)
                                                ? 'low-stock' : ''
                                        }>
                                            {warehouse.inventory ?? 'N/A'}
                                        </span>
                                    </td>
                                    <td style={{ color: '#dc3545', fontWeight: '600' }}>{warehouse.reorder_level ?? 'N/A'}</td>
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
}
