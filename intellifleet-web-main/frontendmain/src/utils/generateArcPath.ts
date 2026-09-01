/**
 * Generates a curved arc path between two points for air routes
 * Uses quadratic bezier curve with control point above midpoint
 */
export function generateArcPath(
    start: { lat: number; lng: number },
    end: { lat: number; lng: number },
    numPoints: number = 50
): { lat: number; lng: number }[] {
    const points: { lat: number; lng: number }[] = [];

    // Calculate distance between points
    const distance = Math.sqrt(
        Math.pow(end.lat - start.lat, 2) + Math.pow(end.lng - start.lng, 2)
    );

    // Control point - midpoint shifted upward for curve effect
    // The curve height is proportional to the distance
    const midLat = (start.lat + end.lat) / 2;
    const midLng = (start.lng + end.lng) / 2;
    const controlLat = midLat + distance * 0.15; // Curve height (adjust for more/less curve)
    const controlLng = midLng;

    for (let i = 0; i <= numPoints; i++) {
        const t = i / numPoints;

        // Quadratic bezier formula: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
        const lat =
            (1 - t) * (1 - t) * start.lat +
            2 * (1 - t) * t * controlLat +
            t * t * end.lat;
        const lng =
            (1 - t) * (1 - t) * start.lng +
            2 * (1 - t) * t * controlLng +
            t * t * end.lng;

        points.push({ lat, lng });
    }

    return points;
}