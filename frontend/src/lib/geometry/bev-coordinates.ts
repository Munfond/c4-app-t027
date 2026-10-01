import type { DetectionSize, EgoPoint, ViewerDetection } from "@/lib/viewer";

/** Ground-plane point where +x is screen-right and +y is screen-up. */
export interface BevPoint {
  x: number;
  y: number;
}

/**
 * Renderer world point for a top-down camera looking along world -Y.
 * World -Z is the top of the default viewport.
 */
export interface BevWorldPoint {
  x: number;
  y: number;
  z: number;
}

export interface BevBoxTransform {
  position: BevWorldPoint;
  size: {
    x: number;
    y: number;
    z: number;
  };
  rotationYRadians: number;
}

export interface EgoBoxFootprint {
  center: EgoPoint;
  size: Pick<DetectionSize, "width" | "length">;
  yawRadians: number;
}

/** Maps ego-forward to screen-up and ego-left to screen-left. */
export function egoPointToBev(
  point: Pick<EgoPoint, "forward" | "left">,
): BevPoint {
  return {
    x: -point.left,
    y: point.forward,
  };
}

/**
 * Maps ego axes to a Y-up renderer world:
 * ego +forward -> world -Z, ego +left -> world -X, ego +up -> world +Y.
 */
export function egoPointToBevWorld(point: EgoPoint): BevWorldPoint {
  return {
    x: -point.left,
    y: point.up,
    z: -point.forward,
  };
}

/**
 * Produces a box transform for geometry whose local axes are width=X,
 * height=Y and length=Z. Positive ego yaw remains positive world-Y rotation.
 */
export function detectionToBevBoxTransform(
  detection: ViewerDetection,
): BevBoxTransform {
  return {
    position: egoPointToBevWorld(detection.center),
    size: {
      x: detection.size.width,
      y: detection.size.height,
      z: detection.size.length,
    },
    rotationYRadians: detection.yawRadians,
  };
}

/** Returns corners ordered front-left, front-right, rear-right, rear-left. */
export function getBevBoxCorners(footprint: EgoBoxFootprint): readonly BevPoint[] {
  const halfLength = footprint.size.length / 2;
  const halfWidth = footprint.size.width / 2;
  const cosine = Math.cos(footprint.yawRadians);
  const sine = Math.sin(footprint.yawRadians);

  const localCorners = [
    { forward: halfLength, left: halfWidth },
    { forward: halfLength, left: -halfWidth },
    { forward: -halfLength, left: -halfWidth },
    { forward: -halfLength, left: halfWidth },
  ] as const;

  return localCorners.map((corner) => {
    const forward =
      footprint.center.forward +
      corner.forward * cosine -
      corner.left * sine;
    const left =
      footprint.center.left +
      corner.forward * sine +
      corner.left * cosine;

    return egoPointToBev({ forward, left });
  });
}
