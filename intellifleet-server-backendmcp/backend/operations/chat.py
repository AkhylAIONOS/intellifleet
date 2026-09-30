"""Conservative deterministic intent adapter; unrecognized planning goes to existing supervisor."""
import re
from datetime import datetime
from backend.fedex.eligibility import IST, evaluate
from backend.fedex.models import EligibilityInput
from .routes import all_movements, schedules_for


def answer(owner,message,selected_id=None):
    text=message.casefold()
    schedule_query = any(w in text for w in ('which service', 'scheduled movement', 'can still reach', 'can catch')) or ('can ' in text and ' catch ' in text)
    operational = any(w in text for w in ('movement', 'active vehicles', 'delayed trucks', 'revised eta',
        'current eta', 'shipment on the map', 'truck is delayed', 'cutoff is missed', 'current location',
        'its progress', 'shipment status', 'current shipment', 'selected shipment', 'delayed shipment',
        'current status', 'happening with'))
    road_query = bool(selected_id) and any(w in text for w in ('fastest road', 'shortest road', 'cheapest route', 'compare fastest', 'road ahead', 'reroute', 'where is the truck'))
    operational = operational or road_query
    result = None
    if not operational and not schedule_query and re.search(r'\b\w+-[\w-]+\b', text):
        result = all_movements({'user_id': owner})['movements']
        operational = any(re.search(r'(?<![\w-])' + re.escape(str(m.get(key, '')).casefold()) + r'(?![\w-])', text)
                          for m in result if m['status'] != 'SCHEDULE_TEMPLATE'
                          for key in ('simulation_id', 'shipment_id') if m.get(key))
    if operational and not schedule_query:
        if result is None: result = all_movements({'user_id': owner})['movements']
        live = [m for m in result if m['status'] != 'SCHEDULE_TEMPLATE' and not m.get('stopped')]
        def mentioned(value):
            return bool(value) and bool(re.search(r'(?<![\w-])' + re.escape(str(value).casefold()) + r'(?![\w-])', text))
        explicit = [m for m in live if mentioned(m['simulation_id']) or mentioned(m['shipment_id'])]
        origins = {m['origin_station'] for m in live if mentioned(m['origin_station'])}
        gateways = {m['gateway'] for m in live if mentioned(m['gateway'])}
        if explicit:
            live = explicit
        else:
            if origins: live = [m for m in live if m['origin_station'] in origins]
            if gateways: live = [m for m in live if m['gateway'] in gateways]
            # Unknown explicit lane must never fall back to the entire collection.
            if re.search(r'\b\w+[\w-]*\s+(?:to|→)\s+\w+', text) and not (origins or gateways):
                return {'success': True, 'response': 'No matching active shipment for that lane. Specify its shipment ID or select a movement.', 'actions': []}
        if re.search(r'\bair\b', text): live = [m for m in live if m['mode'] == 'AIR']
        if re.search(r'\brail\b', text): live = [m for m in live if m['mode'] == 'RAIL']
        if re.search(r'\b(trucks?|surface)\b', text): live = [m for m in live if m['mode'] == 'SURFACE']
        if 'delayed' in text and 'what happens' not in text: live = [m for m in live if m['delay_minutes'] > 0]
        contextual = road_query or any(w in text for w in ('current shipment', 'selected shipment', 'this shipment', 'this truck',
            'its revised', 'its current', 'its progress', 'current status', 'cutoff is missed', 'happening with'))
        if contextual and not explicit and selected_id:
            selected = [m for m in live if m['simulation_id'] == selected_id]
            if selected: live = selected
            elif not (origins or gateways): live = []
        if contextual and len(live) != 1:
            return {'success': True, 'response': 'Specify the shipment ID or select one movement so I can use its authoritative simulation state.', 'actions': []}
        lines = []
        from datetime import timedelta
        def display_time(value):
            return datetime.fromisoformat(value).astimezone(IST).strftime('%d %b %Y, %H:%M IST')
        for m in live[:10]:
            line = (f"Current shipment: {m['shipment_id']} · {m['origin_station']} → {m['gateway']}\n"
                    f"Mode/service: {m['mode']} / {m.get('service', 'Not supplied')}\n"
                    f"Status: {m['status']}; progress {m['progress']:.1%}; delay {m['delay_minutes']:g} min\n"
                    f"Scheduled ETA: {display_time(m['scheduled_eta'])}\nRevised ETA: {display_time(m['current_eta'])}\n"
                    f"Source: {m['data_source']} / DEMO_SIMULATION (synthetic telemetry)")
            if m.get('road_routing_status') == 'READY':
                line += (f"\nMap position: {m['latitude']:.5f}, {m['longitude']:.5f}; "
                         f"{m['distance_travelled_km']:.1f} km travelled, {m['distance_remaining_km']:.1f} km remaining."
                         f"\nRoad route: {m['optimization_mode']} / {m['route_source']}; {m['route_distance_km']:.1f} km. "
                         f"Map travel estimate {m['road_estimated_duration_minutes']:.0f} min; simulation ETA retains the existing plan/schedule timing.")
                if road_query:
                    line += '\nOnly FASTEST is supported by the configured driving profile. Exact shortest/cheapest, toll costs and blocked-segment avoidance are unavailable. No reroute or cost change was applied.'
            elif road_query:
                line += '\nNo road route is attached to this movement. Air/Rail are not routed over roads.'
            if 'what happens' in text:
                match = re.search(r'(\d+)\s*minutes?', text)
                if match:
                    minutes = int(match[1]); revised = datetime.fromisoformat(m['current_eta']) + timedelta(minutes=minutes)
                    line += f'\nHypothetical additional delay: {minutes} min; revised ETA {display_time(revised.isoformat())}. No event applied.'
            alerts = m.get('alerts', [])
            if alerts:
                alert = alerts[-1]
                line += f"\nRecommended action: {alert['recommended_action']}\nRecovery: {alert['reason']}"
            elif any(w in text for w in ('risk', 'recommend', 'action')):
                line += '\nNo disruption recommendation has been generated for this movement.'
            lines.append(line)
        if len(live) > 10: lines.append(f'Showing 10 of {len(live)} matching movements. Filter by mode, lane or shipment ID for details.')
        if 'cutoff is missed' in text and live:
            from backend.fedex.telemetry import runtime
            sim = runtime.get(owner, live[0]['simulation_id'])
            eligible = evaluate(sim.schedules, EligibilityInput(origin_station=sim.request.origin_station, gateway=sim.request.gateway,
                shipment_ready_datetime=sim.now, simulation_date=sim.now.date()))
            alternatives = [c for c in eligible['candidates'] if c['eligible'] and c['schedule_id'] != sim.selected['schedule_id']]
            lines.append('Origin alternatives (requires shipment still at origin): ' + ('; '.join(f"{c['service']} ETA {c['eta']}" for c in alternatives) or 'No confirmed feasible service in this source template.'))
        return {'success': True, 'response': '\n\n'.join(lines) or 'No matching active simulated movements. Open Live Operations to start a demo.',
                'actions': [{'type': 'show_movements', 'data': {'filter': 'AIR' if re.search(r'\bair\b', text) else 'RAIL' if re.search(r'\brail\b', text) else 'SURFACE' if re.search(r'\b(trucks?|surface)\b', text) else 'ALL',
                    'selected': live[0]['simulation_id'] if len(live) == 1 else None}}]}
    if schedule_query:
        source = 'FEDEX' if 'fedex' in text else 'SYNTHETIC'
        if 'synthetic' not in text and source == 'SYNTHETIC':
            from fastapi import HTTPException
            try:
                if any(re.search(r'(?<![\w-])'+re.escape(s.origin_station.casefold())+r'(?![\w-])', text) for s in schedules_for(owner, 'FEDEX')): source = 'FEDEX'
            except HTTPException:
                pass
        ss=schedules_for(owner,source)
        origins={s.origin_station for s in ss if s.origin_station.casefold() in text or s.origin_city.casefold() in text}
        explicit={s.origin_station for s in ss if f'from {s.origin_city.casefold()}' in text or s.origin_station.casefold() in text}
        if explicit: origins=explicit
        candidates=[s for s in ss if s.origin_station in origins]
        gateways={s.gateway for s in candidates if s.gateway.casefold() in text or s.gateway.replace('SYN-','').split('-')[0].casefold() in text}
        if not gateways: gateways={s.gateway for s in candidates}
        match=re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b',text)
        if len(origins)!=1 or len(gateways)!=1 or not match:
            return {'success':True,'response':'Provide origin station, gateway, and ready time HH:MM; include FedEx or synthetic to select provenance.','actions':[]}
        ready=datetime.now(IST).replace(hour=int(match[1]),minute=int(match[2]),second=0,microsecond=0)
        date_match=re.search(r'\d{4}-\d{2}-\d{2}',text)
        if date_match:
            from datetime import date
            ready=datetime.combine(date.fromisoformat(date_match[0]),ready.timetz())
        result=evaluate(ss,EligibilityInput(origin_station=next(iter(origins)),gateway=next(iter(gateways)),shipment_ready_datetime=ready,simulation_date=ready.date()))
        selected=result['selected']
        response=f"{source} template, {ready.date()} IST: "+(f"{selected['service']} / {selected['mode']} run {selected['run']}; cutoff {selected['cutoff']}; ETD {selected['etd']}; ETA {selected['eta']}." if selected else result['selection_reason'])
        return {'success':True,'response':response+' Operating calendar is a template assumption.','actions':[]}
    return None
