"""Canonical operation envelope and typed scenario normalization shared by adapters."""
from datetime import datetime, timedelta
from typing import Any
from pydantic import BaseModel, Field

class CanonicalPlanningIntent(BaseModel):
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    def resolve(self, context: dict) -> dict:
        result = dict(self.parameters)
        changes = dict(result.get('changes') or {})
        if 'risk_delta' in result:
            changes['risk_delta'] = result.pop('risk_delta')
        advance = result.pop('deadline_advance_hours', changes.pop('deadline_advance_hours', None))
        if advance is not None:
            baseline = context.get('deadline') or (context.get('selected_plan') or {}).get('eta')
            if not baseline:
                raise ValueError('A baseline arrival or deadline is required to calculate an earlier delivery target.')
            changes['deadline'] = (datetime.fromisoformat(baseline)-timedelta(hours=float(advance))).isoformat()
        for key in ('fuel_cost_increase_percent', 'fuel_cost_increase_percentage'):
            if key in changes:
                changes['fuel_cost_multiplier'] = 1+float(changes.pop(key))/100
        if changes:
            result['changes'] = changes
        return result
