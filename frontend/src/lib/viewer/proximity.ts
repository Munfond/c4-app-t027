import type { ViewerDetection } from "./types";

/** Ground-plane distance to box centre, not clearance or collision probability. */
export function centreDistance(detection: ViewerDetection): number {
  return Math.hypot(detection.center.forward, detection.center.left);
}

export function proximityColor(detection: ViewerDetection): string {
  const distance = centreDistance(detection);
  return distance < 10 ? "#fb7185" : distance < 25 ? "#fbbf24" : "#2dd4bf";
}
