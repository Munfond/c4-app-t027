import type { BevViewState } from "@/lib/viewer/types";

export const BEV_BASE_FRUSTUM_HEIGHT_METERS = 100;

export interface OrthographicFrustum {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface BevViewportExtent {
  widthMeters: number;
  heightMeters: number;
}

export interface BevWorldTarget {
  x: number;
  z: number;
}

const validAspect = (aspect: number) =>
  Number.isFinite(aspect) && aspect > 0 ? aspect : 1;

export function getOrthographicFrustum(aspect: number): OrthographicFrustum {
  const halfHeight = BEV_BASE_FRUSTUM_HEIGHT_METERS / 2;
  const halfWidth = halfHeight * validAspect(aspect);

  return {
    left: -halfWidth,
    right: halfWidth,
    top: halfHeight,
    bottom: -halfHeight,
  };
}

export function visibleHeightToCameraZoom(visibleHeightMeters: number): number {
  return BEV_BASE_FRUSTUM_HEIGHT_METERS / visibleHeightMeters;
}

export function cameraZoomToVisibleHeight(cameraZoom: number): number {
  return BEV_BASE_FRUSTUM_HEIGHT_METERS / cameraZoom;
}

export function getBevViewportExtent(
  visibleHeightMeters: number,
  aspect: number,
): BevViewportExtent {
  return {
    widthMeters: visibleHeightMeters * validAspect(aspect),
    heightMeters: visibleHeightMeters,
  };
}

export function bevCenterToWorldTarget(
  center: BevViewState["center"],
): BevWorldTarget {
  return {
    x: -center.left,
    z: -center.forward,
  };
}

export function worldTargetToBevCenter(
  target: BevWorldTarget,
): BevViewState["center"] {
  return {
    forward: -target.z,
    left: -target.x,
  };
}
