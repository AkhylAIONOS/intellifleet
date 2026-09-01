// import { Marker, Popup } from 'react-leaflet';
// import L from 'leaflet';
// import { useAppStore } from '../../store/appStore';
// import './WarehousePopup.css';

// // Custom Warehouse Icon
// // const warehouseIcon = new L.Icon({
// //     iconUrl: 'icons/location.png',
// //     iconSize: [32, 32],
// //     iconAnchor: [16, 48],     // Bottom center of the icon
// //     popupAnchor: [0, -40],    // Popup appears above the icon
// // });
// const warehouseIcon = new L.Icon({
//     iconUrl: 'icons/location.png',
//     iconSize: [28, 28],
//     iconAnchor: [14, 28],   // ✔ bottom-center
//     popupAnchor: [0, -28],
// });

// export const WarehousesLayer = () => {
//     const { warehouses } = useAppStore();

//     return (
//         <>
//             {warehouses.map((warehouse) => (
//                 <Marker
//                     key={warehouse.id}
//                     position={[warehouse.latitude, warehouse.longitude]}
//                     icon={warehouseIcon}
//                 >
//                     <Popup>
//                         <div className="warehouse-popup">
//                             <h3>{warehouse.name}</h3>
//                             <p>{warehouse.address}</p>
//                             <div className="vehicle-counts">
//                                 <small>Trucks: {warehouse.vehicles?.trucks || 0}</small>
//                                 <br />
//                                 <small>Cars: {warehouse.vehicles?.cars || 0}</small>
//                                 <br />
//                                 <small>Bikes: {warehouse.vehicles?.bikes || 0}</small>
//                                 <br />
//                                 <small>Autos: {warehouse.vehicles?.autos || 0}</small>
//                             </div>
//                         </div>
//                     </Popup>
//                 </Marker>
//             ))}
//         </>
//     );
// };


import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { useAppStore } from '../../store/appStore';
import './WarehousePopup.css';

// Active Warehouse Icon
const warehouseIcon = new L.Icon({
    iconUrl: 'icons/location.png',
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -28],
});

// Inactive Warehouse Icon (with cross overlay)
const inactiveWarehouseIcon = new L.DivIcon({
    className: 'inactive-warehouse-icon',
    html: `
        <div style="position: relative; width: 28px; height: 28px;">
            <img src="icons/location.png" style="width: 28px; height: 28px;" />
            <img src="icons/close.png" style="position: absolute; top: 0; left: 0; width: 28px; height: 28px;" />
        </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -28],
});

export const WarehousesLayer = () => {
    const warehouses = useAppStore(state => state.warehouses);

    // Filter out warehouses with invalid coordinates
    const validWarehouses = warehouses.filter(
        (w) => w.latitude != null && w.longitude != null && !isNaN(w.latitude) && !isNaN(w.longitude)
    );

    return (
        <>
            {validWarehouses.map((warehouse) => {
                const isActive = warehouse.is_active === 1;

                return (
                    <Marker
                        key={warehouse.id}
                        position={[warehouse.latitude, warehouse.longitude]}
                        icon={isActive ? warehouseIcon : inactiveWarehouseIcon}
                    >
                        <Popup>
                            <div className="warehouse-popup">
                                <h3>{warehouse.name}</h3>
                                <p>{warehouse.address}</p>
                                {!isActive && (
                                    <p style={{ color: '#dc3545', fontWeight: 'bold' }}>
                                        ⚠️ Non-Functional
                                    </p>
                                )}
                                {/* <div className="vehicle-counts">
                                    <small>Trucks: {warehouse.vehicles?.trucks || 0}</small>
                                    <br />
                                    <small>Cars: {warehouse.vehicles?.cars || 0}</small>
                                    <br />
                                    <small>Bikes: {warehouse.vehicles?.bikes || 0}</small>
                                    <br />
                                    <small>Autos: {warehouse.vehicles?.autos || 0}</small>
                                </div> */}
                            </div>
                        </Popup>
                    </Marker>
                );
            })}
        </>
    );
};