/** Display only: preserve timetable-only values; convert aware instants to IST. */
export function operationalTime(value: string | number | null | undefined): string {
  if (value == null || value === '') return 'Unavailable';
  if (typeof value === 'string' && !/T.*(?:Z|[+-]\d{2}:?\d{2})$/.test(value)) return value;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Unavailable';
  return new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata',year:'numeric',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date) + ' IST';
}
