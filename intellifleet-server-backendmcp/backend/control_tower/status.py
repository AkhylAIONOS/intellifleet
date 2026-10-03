from datetime import datetime, timezone


def timestamp(value):
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Operational timestamps require a timezone offset')
    return parsed.astimezone(timezone.utc)


def operational_fields(run, now=None, tolerance_minutes=5):
    """Arrival wins; overdue planned arrival is delayed; future lateness expected.

    Missing actual departure never implies a departure scan. Synthetic callers
    must provide their own labelled actual timestamps and synthetic clock.
    """
    now = timestamp(now or datetime.now(timezone.utc))
    departure = timestamp(run.get('actual_departure_at'))
    arrival = timestamp(run.get('actual_arrival_at'))
    planned = timestamp(run.get('planned_eta'))
    current = timestamp(run.get('current_eta')) or planned
    from datetime import timedelta
    tolerance = timedelta(minutes=tolerance_minutes)
    if arrival:
        status = 'ARRIVED'
    elif departure is None or departure > now:
        status = 'SCHEDULED'
    elif planned and now > planned+tolerance:
        status = 'DELAYED'
    elif planned and current and current > planned+tolerance:
        status = 'EXPECTED DELAY'
    else:
        status = 'ON TIME'
    elapsed = None if departure is None or departure > now else max(0, ((arrival or now)-departure).total_seconds()/3600)
    remaining = 0.0 if arrival else max(0, (current-now).total_seconds()/3600) if departure and departure<=now and current else None
    actual_tt = (arrival-departure).total_seconds()/3600 if arrival and departure else None
    delay = max(0, ((arrival or current)-planned).total_seconds()/3600) if planned and (arrival or current) else None
    deadline = timestamp(run.get('deadline'))
    return dict(status=status, elapsed_hours=round(elapsed,4) if elapsed is not None else None,
                estimated_time_left_hours=round(remaining,4) if remaining is not None else None,
                actual_tt_hours=round(actual_tt,4) if actual_tt is not None else None,
                delay_hours=round(delay,4) if delay is not None else None,
                baseline_sla_met=(planned<=deadline) if planned and deadline else None,
                current_sla_met=((arrival or current)<=deadline) if (arrival or current) and deadline else None,
                calculated_source='CALCULATED')
