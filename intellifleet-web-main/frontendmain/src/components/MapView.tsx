import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet';
import { useEffect } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './MapView.css';
import { WarehousesLayer } from './MapLayers/WarehousesLayer';
import { RoutesLayer } from './MapLayers/RoutesLayer';
import { VehiclesLayer } from './MapLayers/VehiclesLayer';
import { indiaBoundary } from '../assets/india-boundary';
import { useAppStore } from '../store/appStore';
import type { Warehouse } from '../types/api';
import { GuardedJourney } from './JourneyBoundary';
import { WarehouseFocusLayer } from './MapLayers/WarehouseFocusLayer';
import { MapLegend } from './MapLayers/MapLegend';
import { PlanesLayer } from './MapLayers/PlanesLayer';
import { decodePolyline } from '../utils/decodePolyline';


// Fix for default marker icons in React-Leaflet
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// Helper function to calculate bounds from warehouses
const calculateWarehouseBounds = (warehouses: Warehouse[]) => {
  // Filter out warehouses with invalid coordinates
  const validWarehouses = warehouses.filter(
    w => w.latitude && w.longitude && w.latitude !== 0 && w.longitude !== 0
  );

  if (validWarehouses.length === 0) return null;

  // Get all coordinates
  const coordinates = validWarehouses.map(w => [w.latitude, w.longitude] as [number, number]);

  // Return Leaflet bounds
  return L.latLngBounds(coordinates);
};

// Component to control map zoom based on warehouses
// const MapController = () => {
//   const map = useMap();
//   const { warehouses } = useAppStore();

//   useEffect(() => {
//     if (warehouses.length > 0) {
//       const bounds = calculateWarehouseBounds(warehouses);

//       if (bounds) {
//         if (warehouses.length === 1) {
//           // Single warehouse: center on it with fixed zoom
//           const warehouse = warehouses[0];
//           map.setView([warehouse.latitude, warehouse.longitude], 12, { animate: true });
//         } else {
//           // Multiple warehouses: fit all in view
//           map.fitBounds(bounds, {
//             padding: [50, 50],
//             animate: true,
//             duration: 1.0
//           });
//         }
//       }
//     }
//   }, [warehouses, map]);

//   return null; // This component doesn't render anything
// };

// Component to zoom when a vehicle is assigned to a route
const VehicleAssignmentZoomController = () => {
  const map = useMap();
  const activeRoutes = useAppStore(state => state.activeRoutes);
  const lastAssignedRouteId = useAppStore(state => state.lastAssignedRouteId);
  const setLastAssignedRouteId = useAppStore(state => state.setLastAssignedRouteId);

  useEffect(() => {
    if (lastAssignedRouteId === null) return;

    const route = activeRoutes[lastAssignedRouteId];
    if (!route || route.routeData?.planning || useAppStore.getState().selectedPlan) return;

    const bounds = L.latLngBounds([]);
    let hasValidBounds = false;

    // Handle regular routes
    const rawPath = route.routeData?.optimal_routes?.[0]?.path;
    if (rawPath) {
      const pathPoints = typeof rawPath === 'string' ? decodePolyline(rawPath) : rawPath;
      pathPoints.forEach((p: any) => {
        bounds.extend([p.lat, p.lng]);
        hasValidBounds = true;
      });
    }

    // Handle multimodal routes
    if (route.routeData?.multimodal && route.routeData?.segments) {
      const segments = route.routeData.segments;
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

    // Clear the trigger so it doesn't re-zoom on every render
    setLastAssignedRouteId(null);

  }, [lastAssignedRouteId, activeRoutes, map, setLastAssignedRouteId]);

  return null;
};
// Component to control map zoom based on warehouses
const MapController = () => {
  const map = useMap();
  const warehouses = useAppStore(state => state.warehouses);
  const activeRoutes = useAppStore(state => state.activeRoutes);

  useEffect(() => {
    // Only zoom to warehouses if there are NO active routes
    // (If there are routes, RoutesLayer takes care of zooming)
    const hasRoutes = Object.keys(activeRoutes).length > 0;

    if (warehouses.length > 0 && !hasRoutes) {
      const bounds = calculateWarehouseBounds(warehouses);

      if (bounds) {
        if (warehouses.length === 1) {
          // Single warehouse: center on it with fixed zoom
          const warehouse = warehouses[0];
          map.setView([warehouse.latitude, warehouse.longitude], 12, { animate: true });
        } else {
          // Multiple warehouses: fit all in view
          map.fitBounds(bounds, {
            padding: [50, 50],
            animate: true,
            duration: 1.0
          });
        }
      }
    }
  }, [warehouses, map, activeRoutes]); // Added activeRoutes to dependency array

  return null;
};
export const MapView = () => {
  // Default center: India
  const center: [number, number] = [20.5937, 78.9629];
  const zoom = 5;
  const mapViewMode = useAppStore(state => state.mapViewMode);

  //india boundary kashmir logic


  return (
    <div className="map-view">
      <MapContainer center={center} zoom={zoom} style={{ height: '100%', width: '100%' }}>
        {/* Map Controller for auto-zoom */}
        <MapController />

        {/* INDIA BOUNDARY OVERLAY */}
        <GeoJSON
          data={indiaBoundary as any}
          style={(feature) => {
            const boundaryType = feature?.properties?.boundary;
            //console.log('Styling boundary:', boundaryType);

            // TESTING: INVERTED LOGIC
            // Making disputed = off-white (invisible)
            // Making claimed = dark gray (visible)
            if (boundaryType === 'disputed') {
              return {
                color: '#f5f5f5',     // Off-white
                weight: 1,
                fillColor: 'transparent',
                fillOpacity: 0,
                opacity: 0.2          // Nearly invisible
              };
            }

            // Claimed = dark and visible
            return {
              color: '#6e6e6e',       // Dark gray
              weight: 2,
              fillColor: 'transparent',
              fillOpacity: 0,
              opacity: 0.9            // Clearly visible
            };
          }}
        />

        {mapViewMode === 'street' ? (
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        ) : (
          <TileLayer
            attribution='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
        )}
        <WarehousesLayer />
        <RoutesLayer />
        <VehiclesLayer />
        <PlanesLayer />
        <VehicleAssignmentZoomController />
        <GuardedJourney />
        <WarehouseFocusLayer />
        <MapLegend />
      </MapContainer>
    </div>
  );
};

