import L from 'leaflet';
import { useAppStore } from '../../store/appStore';
import { AnimatedVehicleMarker } from './AnimatedVehicleMarker';
//import { useShallow } from 'zustand/react/shallow';

// Helper to get icon based on type
const getVehicleIcon = (type: string, isMoving: boolean) => {
    const typeLower = type.toLowerCase();
    let iconUrl = '';

    // Use different icons based on type
    // Note: In a real production app, these should be local assets or reliable CDN links
    // Using placeholder icons for demonstration
    if (typeLower.includes('truck')) {
        iconUrl = 'https://i.ibb.co/RGhSqf6x/Pngtree-truck-top-view-8488344-1-2-1.png'; // Truck icon
    } else if (typeLower.includes('bike') || typeLower.includes('motorcycle')) {
        iconUrl = 'https://i.ibb.co/j9HHbB92/bike.png'; // Bike icon
    } else if (typeLower.includes('auto') || typeLower.includes('rickshaw')) {
        iconUrl = 'https://i.ibb.co/whqfyJD7/auto.png'; // Auto icon
    } else if (typeLower.includes('car')) {
        iconUrl = 'https://cdn-icons-png.flaticon.com/512/12689/12689302.png'; // CAR icon
    } else if (typeLower.includes('plane')) {
        // Plane icon - return null since planes use PlaneMarker component
        return null;
    } else {
        iconUrl = 'https://i.ibb.co/RGhSqf6x/Pngtree-truck-top-view-8488344-1-2-1.png'; // Truck Icon (default)
    }

    return new L.Icon({
        iconUrl: iconUrl,
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        popupAnchor: [0, -16],
        shadowSize: [32, 32],
        className: isMoving ? 'vehicle-moving-icon' : ''
    });
};

// export const VehiclesLayer = () => {
//     const { vehicles } = useAppStore();

//     return (
//         <>
//             {vehicles.map((vehicle) => {
//                 // Only show vehicles that are currently assigned to a route
//                 // Show both assigned AND completed vehicles (completed stay at destination)
//                 if ((vehicle.status !== 'assigned' && vehicle.status !== 'completed') || !vehicle.assigned_route) return null;

//                 return (
//                     <AnimatedVehicleMarker
//                         key={vehicle.id}
//                         vehicle={vehicle}
//                         iconFactory={getVehicleIcon}
//                     />
//                 );
//             })}
//         </>
//     );
// };

export const VehiclesLayer = () => {
    const vehicles = useAppStore(state => state.vehicles);

    return (
        <>
            {vehicles.map((vehicle) => {
                // Only show vehicles that are currently assigned to a route
                // Show both assigned AND completed vehicles (completed stay at destination)
                if ((vehicle.status !== 'assigned' && vehicle.status !== 'completed') || !vehicle.assigned_route) return null;

                // Skip planes - they are rendered by PlanesLayer
                if (vehicle.type === 'plane') return null;

                return (
                    <AnimatedVehicleMarker
                        key={vehicle.id}
                        vehicle={vehicle}
                        iconFactory={getVehicleIcon}
                    />
                );
            })}
        </>
    );
};
