import {useEffect} from 'react';
import {type VisualPlan} from '../../utils/planVisuals';
import {ensurePlanMovement} from '../../utils/planMovement';

// The central runtime owns the journey; selection/unmount never resets it.
export function RoadPlanJourney({plan}:{plan:VisualPlan}) {
  useEffect(()=>{void ensurePlanMovement(plan);},[plan.plan_id]);
  return null;
}
