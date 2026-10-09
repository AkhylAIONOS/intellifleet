import {movementIcon} from './movementIcon';
import { Marker, Popup } from 'react-leaflet';
import { useAppStore } from '../../store/appStore';
import { AnimatedVehicleMarker } from './AnimatedVehicleMarker';
//import { useShallow } from 'zustand/react/shallow';

// Helper to get icon based on type
const getVehicleIcon = (type: string, _isMoving: boolean) => type.toLowerCase().includes('plane')?null:movementIcon('SURFACE');

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
    const selectedPlan = useAppStore(state => state.selectedPlan);

    return (
        <>
            {vehicles.map((vehicle) => {
                // Only show vehicles that are currently assigned to a route
                // Show both assigned AND completed vehicles (completed stay at destination)
                if ((vehicle.status !== 'assigned' && vehicle.status !== 'completed') || !vehicle.assigned_route) return null;

                // Skip planes - they are rendered by PlanesLayer
                if (String(vehicle.type).toLowerCase() === 'plane') return null;

                if (vehicle.assigned_route.route_data?.planning) return null;
                if (selectedPlan) {
                    const icon = getVehicleIcon(vehicle.type, false);
                    if (!icon || !Number.isFinite(vehicle.current_position?.lat) || !Number.isFinite(vehicle.current_position?.lng)) return null;
                    return <Marker key={vehicle.id} position={vehicle.current_position} icon={icon}>
                        <Popup><b>{vehicle.label}</b><br />{vehicle.type}{vehicle.capacity != null && <><br />Capacity: {vehicle.capacity} kg</>}</Popup>
                    </Marker>;
                }

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
