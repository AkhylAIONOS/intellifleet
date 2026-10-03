"""Deterministic metric corrections; no model calls or network side effects."""
import math


def number(row, key, default=0.0):
    value = row.get(key)
    return default if value is None else float(value)


def unit(value):
    return min(1.0, max(0.0, value)) if math.isfinite(value) else 1.0


def risk(legs, utilization, vehicles=None, warehouses=None, changes=None):
    if not legs:
        return dict(route=1.0, vehicle=1.0, weather=0.0, warehouse=0.0, mode=1.0, overall=1.0)
    modes = {x.get('route_type', 'road') for x in legs}
    route = unit(sum(1-number(x, 'reliability', .9)+number(x, 'operational_risk') for x in legs)/len(legs)
                 + min(max(0, sum(number(x, 'distance') for x in legs))/10000, .15)
                 + number(changes or {}, 'risk_delta'))
    weather = unit(sum(number(x, 'weather_risk') for x in legs)/len(legs))
    vehicle = unit((sum(1-number(v, 'reliability', .9)+number(v, 'breakdown_risk') for v in vehicles)/len(vehicles)
                    if vehicles else .25) + max(0, utilization-.9)*.25)
    warehouse = unit(sum(1-number(w, 'reliability', .9)+number(w, 'disruption_risk') for w in warehouses)/len(warehouses)) if warehouses else .1
    mode = unit(sum({'road':.18, 'air':.10, 'multimodal':.14}.get(m, .2) for m in modes)/len(modes))
    overall = unit(.35*route+.25*vehicle+.15*weather+.10*warehouse+.15*mode)
    return {k:round(v, 4) for k,v in dict(route=route,vehicle=vehicle,weather=weather,warehouse=warehouse,mode=mode,overall=overall).items()}


def additional_air_cost(leg):
    amount = number(leg, 'air_cost')
    # The original CSV adapter duplicated the SAME base amount into air_cost.
    # Explicit additional charges can opt out; other Air charges are retained.
    base = leg.get('base_transport_cost')
    if leg.get('route_type') == 'air' and base is not None and amount == float(base) and not leg.get('air_cost_is_additional'):
        return 0.0
    return amount
