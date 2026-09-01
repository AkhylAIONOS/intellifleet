/**
 * Converts decimal hours to a human-readable format like "1 hr 30 min"
 * @param decimalHours - Duration in decimal hours (e.g., 1.5, 2.3334)
 * @returns Formatted string like "1 hr 30 min"
 */
export function formatDuration(decimalHours: number | string | undefined): string {
    if (decimalHours === undefined || decimalHours === null) {
        return 'N/A';
    }

    // Convert to number if it's a string
    const hours = typeof decimalHours === 'string' ? parseFloat(decimalHours) : decimalHours;

    if (isNaN(hours)) {
        return 'N/A';
    }

    const wholeHours = Math.floor(hours);
    const minutes = Math.round((hours - wholeHours) * 60);

    if (wholeHours === 0 && minutes === 0) {
        return '0 min';
    }

    if (wholeHours === 0) {
        return `${minutes} min`;
    }

    if (minutes === 0) {
        return `${wholeHours} hr`;
    }

    return `${wholeHours} hr ${minutes} min`;
}