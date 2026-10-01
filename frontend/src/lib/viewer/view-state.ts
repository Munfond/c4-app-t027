import type { BevLayerVisibility, BevViewState } from "./types";

export const DEFAULT_BEV_VIEW_STATE = {
  center: {
    forward: 20,
    left: 0,
  },
  visibleHeightMeters: 100,
} as const satisfies BevViewState;

export const BEV_VIEW_BOUNDS = {
  minVisibleHeightMeters: 20,
  maxVisibleHeightMeters: 300,
  maxCenterDistanceMeters: 1_000,
} as const;

export const DEFAULT_BEV_LAYERS = {
  detections: true,
  confidence: true,
  grid: true,
  egoMarker: true,
} as const satisfies BevLayerVisibility;

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

const finiteOr = (value: number, fallback: number) =>
  Number.isFinite(value) ? value : fallback;

/** Constrains external or control-produced view state to the canonical bounds. */
export function constrainBevViewState(view: BevViewState): BevViewState {
  const maxCenter = BEV_VIEW_BOUNDS.maxCenterDistanceMeters;

  return {
    center: {
      forward: clamp(
        finiteOr(view.center.forward, DEFAULT_BEV_VIEW_STATE.center.forward),
        -maxCenter,
        maxCenter,
      ),
      left: clamp(
        finiteOr(view.center.left, DEFAULT_BEV_VIEW_STATE.center.left),
        -maxCenter,
        maxCenter,
      ),
    },
    visibleHeightMeters: clamp(
      finiteOr(
        view.visibleHeightMeters,
        DEFAULT_BEV_VIEW_STATE.visibleHeightMeters,
      ),
      BEV_VIEW_BOUNDS.minVisibleHeightMeters,
      BEV_VIEW_BOUNDS.maxVisibleHeightMeters,
    ),
  };
}

/** Numeric comparison used later to prevent synchronized-control feedback. */
export function areBevViewStatesEquivalent(
  first: BevViewState,
  second: BevViewState,
  tolerance = 1e-4,
): boolean {
  return (
    Math.abs(first.center.forward - second.center.forward) <= tolerance &&
    Math.abs(first.center.left - second.center.left) <= tolerance &&
    Math.abs(first.visibleHeightMeters - second.visibleHeightMeters) <= tolerance
  );
}
