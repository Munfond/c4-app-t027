export const RADAR_SPEED_COLORS = ["#f0dda2", "#ffbd72", "#fa7f6e"] as const;

export function radarSpeed(point: readonly number[]) { return Math.hypot(point[3], point[4]); }
export function radarDistance(point: readonly number[]) { return Math.hypot(point[0], point[1]); }
export function radarColor(point: readonly number[]) {
  const speed = radarSpeed(point);
  return RADAR_SPEED_COLORS[speed < .5 ? 0 : speed <= 2 ? 1 : 2];
}
// Shared Three.js view: -left is x, up is y, -forward is z.
export function radarVector3D(point: readonly number[]) {
  return {
    start: [-point[1], point[2], -point[0]] as const,
    end: [-point[1] - point[4], point[2], -point[0] - point[3]] as const,
  };
}
export function radarReturns(points: readonly number[][], range: number, movingOnly: boolean) {
  return points.map((point, index) => ({ point, index, distance: radarDistance(point), speed: radarSpeed(point) }))
    .filter(echo => echo.distance <= range && (!movingOnly || echo.speed >= .5))
    .sort((a, b) => a.distance - b.distance);
}
