import { journeyPosition, journeySegments, type VisualPlan } from './planVisuals';

// One scheduler for the entire selected shipment, independent of React and live tracking APIs.
export function playJourney(plan: VisualPlan, onPosition: (position: NonNullable<ReturnType<typeof journeyPosition>>) => void,
  scheduler = {
    request: (callback: FrameRequestCallback) => window.requestAnimationFrame(callback),
    cancel: (id: number) => window.cancelAnimationFrame(id),
  }, reducedMotion = false, onError?: (error: Error) => void) {
  const segments = journeySegments(plan);
  let frame = 0;
  let stopped = false;
  let started: number | undefined;
  const emit = (progress: number) => { const position = journeyPosition(segments, progress); if (position) onPosition(position); };
  emit(reducedMotion ? 1 : 0);
  if (!reducedMotion && segments.length) {
    const tick = (time: number) => {
      if (stopped) return;
      started ??= time;
      const progress = Math.min(1, (time - started) / 10000);
      try {
        emit(progress);
        if (progress < 1) frame = scheduler.request(tick);
      } catch (error) {
        stopped = true;
        if (onError) onError(error instanceof Error ? error : new Error(String(error)));
        else throw error;
        return;
      }
    };
    frame = scheduler.request(tick);
  }
  return () => { stopped = true; scheduler.cancel(frame); };
}
