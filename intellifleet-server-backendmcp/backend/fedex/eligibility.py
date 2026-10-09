from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import EligibilityInput, Schedule

IST = ZoneInfo('Asia/Kolkata')
TEMPLATE_NOTICE = ('Provided schedule template applied to the selected handover date; operating days are unknown. '
                   'Asia/Kolkata is an explicit demo timezone assumption, not workbook metadata. '
                   'A departure earlier than handover rolls to the following day.')


def local_datetime(value):
    return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)


def candidate(schedule: Schedule, request: EligibilityInput):
    start = datetime.combine(request.simulation_date, time(), IST)
    cutoff = start + timedelta(minutes=schedule.cutoff_minutes) if schedule.cutoff_minutes is not None else None
    etd = start + timedelta(minutes=schedule.etd_minutes) if schedule.etd_minutes is not None else None
    if etd and cutoff and etd < cutoff:
        etd += timedelta(days=1)
    eta = etd.replace(hour=schedule.eta_minutes // 60, minute=schedule.eta_minutes % 60) if etd and schedule.eta_minutes is not None else None
    if eta and schedule.eta_day_offset is not None:
        eta = start + timedelta(days=schedule.eta_day_offset, minutes=schedule.eta_minutes)
    if eta and eta < etd:
        eta += timedelta(days=1)
    retrieval = eta.replace(hour=schedule.retrieval_minutes // 60, minute=schedule.retrieval_minutes % 60) if eta and schedule.retrieval_minutes is not None else None
    if retrieval and retrieval < eta:
        retrieval += timedelta(days=1)
    ready = local_datetime(request.shipment_ready_datetime)
    label = f'{schedule.mode} Run {schedule.run}'
    eligible = False
    if not schedule.valid:
        reason = f'{label} is not eligible: source data requires validation; see warnings.'
    elif cutoff is None:
        reason = f'{label} eligibility is unknown: origin handover/cutoff unavailable.'
    elif ready > cutoff:
        reason = f'{label} is not eligible because shipment ready time {ready.strftime("%d %b %Y, %H:%M IST")} is after handover cutoff {cutoff.strftime("%d %b %Y, %H:%M IST")}.'
    elif etd is None or eta is None or eta <= etd:
        reason = f'{label} is not eligible: invalid or ambiguous departure/arrival timing.'
    elif ready > etd:
        reason = f'{label} is not eligible: shipment is ready after departure.'
    else:
        eligible = True
        reason = f'{label} is eligible: shipment ready by handover cutoff and departure.'
    return dict(schedule_id=schedule.schedule_id, origin=schedule.origin_station, gateway=schedule.gateway,
                data_source=schedule.data_source, mode=schedule.mode, run=schedule.run, service=schedule.service, cutoff=cutoff, etd=etd, eta=eta,
                retrieval=retrieval, transit_minutes=schedule.transit_minutes, eligible=eligible, reason=reason,
                warnings=schedule.warnings, source_sheet=schedule.source_sheet, source_row=schedule.source_row)


def evaluate(schedules, request: EligibilityInput):
    candidates = [candidate(s, request) for s in schedules
                  if s.origin_station.casefold() == request.origin_station.casefold() and s.gateway.casefold() == request.gateway.casefold()]
    feasible = sorted((c for c in candidates if c['eligible']), key=lambda c: (c['eta'], c['etd'], c['schedule_id']))
    next_eligible=None
    if not feasible and candidates:
        next_day=max(request.simulation_date+timedelta(days=1),local_datetime(request.shipment_ready_datetime).date())
        future=request.model_copy(update={'simulation_date':next_day})
        future_candidates=[candidate(s,future) for s in schedules if s.origin_station.casefold()==request.origin_station.casefold() and s.gateway.casefold()==request.gateway.casefold()]
        next_eligible=next(iter(sorted((c for c in future_candidates if c['eligible']),key=lambda c:(c['eta'],c['etd'],c['schedule_id']))),None)
    return {'next_eligible':next_eligible,'candidates': candidates, 'selected': feasible[0] if feasible else None,
            'selection_reason': 'Earliest scheduled arrival among eligible provided services; no mode priority.' if feasible else 'No confirmed eligible service in the selected schedule template.',
            'schedule_notice': TEMPLATE_NOTICE, 'timezone': 'Asia/Kolkata'}
