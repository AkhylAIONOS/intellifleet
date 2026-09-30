"""Canonical operation envelope and typed scenario normalization shared by adapters."""
from datetime import datetime, timedelta
import re
from typing import Any
from pydantic import BaseModel, Field
from .models import normalize_modes



def explicit_multimodal_request(message: str) -> bool:
    """Detect requests that require a mixed Road + Air journey."""
    text = str(message or "").casefold()

    if re.search(r"\b(?:multimodal|multi-modal|multi modal)\b", text):
        return True

    # Covers Ground → Air → Ground and equivalent natural-language wording.
    if (
        re.search(r"\b(?:ground|road|surface|truck)\b", text)
        and re.search(r"\b(?:air|airway|flight|aircraft)\b", text)
        and re.search(
            r"(?:ground|road|surface|truck).{0,40}(?:air|airway|flight|aircraft).{0,40}(?:ground|road|surface|truck)",
            text,
            re.I,
        )
    ):
        return True

    return bool(re.search(r'part\s+(?:road|ground|surface).{0,30}part\s+(?:air|flight)',text))


class CanonicalPlanningIntent(BaseModel):
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    def resolve(self, context: dict) -> dict:
        result = dict(self.parameters)
        changes = dict(result.get('changes') or {})
        for values in (result, changes):
            if 'allowed_modes' in values:
                values['allowed_modes'] = normalize_modes(values['allowed_modes'])
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
