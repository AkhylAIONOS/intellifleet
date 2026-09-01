import type { RoutePoint } from '../types/api';

// Calculate bearing between two points in degrees
export const calculateBearing = (start: RoutePoint, end: RoutePoint): number => {
    const startLat = toRad(start.lat);
    const startLng = toRad(start.lng);
    const endLat = toRad(end.lat);
    const endLng = toRad(end.lng);

    const dLng = endLng - startLng;

    const y = Math.sin(dLng) * Math.cos(endLat);
    const x = Math.cos(startLat) * Math.sin(endLat) -
        Math.sin(startLat) * Math.cos(endLat) * Math.cos(dLng);

    let bearing = toDeg(Math.atan2(y, x));
    return (bearing + 360) % 360;
};

// Interpolate position between two points based on fraction (0 to 1)
export const interpolatePosition = (start: RoutePoint, end: RoutePoint, fraction: number): RoutePoint => {
    return {
        lat: start.lat + (end.lat - start.lat) * fraction,
        lng: start.lng + (end.lng - start.lng) * fraction
    };
};

// Calculate distance between two points in meters (Haversine formula)
export const calculateDistance = (p1: RoutePoint, p2: RoutePoint): number => {
    const R = 6371e3; // Earth radius in meters
    const phi1 = toRad(p1.lat);
    const phi2 = toRad(p2.lat);
    const dPhi = toRad(p2.lat - p1.lat);
    const dLambda = toRad(p2.lng - p1.lng);

    const a = Math.sin(dPhi / 2) * Math.sin(dPhi / 2) +
        Math.cos(phi1) * Math.cos(phi2) *
        Math.sin(dLambda / 2) * Math.sin(dLambda / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return R * c;
};

const toRad = (deg: number) => deg * Math.PI / 180;
const toDeg = (rad: number) => rad * 180 / Math.PI;
