import type { ViewerDetection } from "./types";

export type SpatialSurface = "ground" | "raised" | "obstacle";
export type FacadePatch = { forward: number; left: number; bottom: number; height: number; length: number; yaw: number };
export type SpatialSurfaces = {
  groundHeight: number;
  groups: Record<SpatialSurface, number[][]>;
  groundVertices: number[];
  facades: FacadePatch[];
};

/** Local measured surfaces, with unknown cells left open. No semantic labels are inferred. */
export function reconstructSpatialSurfaces(points: readonly number[][], detections: readonly ViewerDetection[]): SpatialSurfaces {
  const valid = points.filter(point => point.length === 3 && point.every(Number.isFinite));
  const heights = valid.filter(([x, y]) => Math.hypot(x, y) < 25).map(point => point[2]).sort((a, b) => a - b);
  const groundHeight = heights[Math.floor(heights.length * 0.15)] ?? 0;
  const boxes = detections.map(d => ({
    ...d.center, cosine: Math.cos(d.yawRadians), sine: Math.sin(d.yawRadians),
    halfLength: d.size.length / 2 + 0.12, halfWidth: d.size.width / 2 + 0.12, halfHeight: d.size.height / 2 + 0.12,
  }));
  const groups: Record<SpatialSurface, number[][]> = { ground: [], raised: [], obstacle: [] };
  for (const point of valid) {
    const [x, y, z] = point;
    const inside = boxes.some(box => {
      if (Math.abs(z - box.up) > box.halfHeight) return false;
      const dx = x - box.forward, dy = y - box.left;
      return Math.abs(dx * box.cosine + dy * box.sine) <= box.halfLength
        && Math.abs(-dx * box.sine + dy * box.cosine) <= box.halfWidth;
    });
    groups[inside ? "obstacle" : z < groundHeight + 0.35 ? "ground" : "raised"].push(point);
  }

  // One-metre cells only where ground returns exist. Corner heights are shared
  // across neighbouring observed cells; gaps and sharp height changes stay open.
  const cells = new Map<string, { x: number; y: number; heights: number[]; z: number }>();
  for (const [x, y, z] of groups.ground) {
    const ix = Math.floor(x), iy = Math.floor(y), key = `${ix}:${iy}`;
    const cell = cells.get(key) ?? { x: ix, y: iy, heights: [], z: 0 };
    cell.heights.push(z); cells.set(key, cell);
  }
  for (const cell of cells.values()) {
    cell.heights.sort((a, b) => a - b);
    cell.z = cell.heights[Math.floor(cell.heights.length / 2)];
  }
  const cornerHeight = (x: number, y: number, fallback: number) => {
    const values: number[] = [];
    for (const ix of [x - 1, x]) for (const iy of [y - 1, y]) {
      const value = cells.get(`${ix}:${iy}`)?.z;
      if (value !== undefined && Math.abs(value - fallback) <= 0.35) values.push(value);
    }
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : fallback;
  };
  const groundVertices: number[] = [];
  for (const { x, y, z } of cells.values()) {
    const corners = [[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1]];
    for (const index of [0, 1, 2, 0, 2, 3]) {
      const [forward, left] = corners[index];
      groundVertices.push(-left, cornerHeight(forward, left, z) - 0.025, -forward);
    }
  }

  // Tall, locally planar clusters support facade patches. Sparse isolated points,
  // cars and people do not become building blocks; no roofs/hidden sides are filled.
  const resolution = 1.2;
  const columns = new Map<string, number[][]>();
  for (const point of groups.raised) {
    const key = `${Math.floor(point[0] / resolution)}:${Math.floor(point[1] / resolution)}`;
    const column = columns.get(key) ?? []; column.push(point); columns.set(key, column);
  }
  const facades: FacadePatch[] = [];
  for (const [key, column] of columns) {
    if (column.length < 3) continue;
    const zValues = column.map(p => p[2]).sort((a, b) => a - b);
    const bottom = zValues[0], top = zValues[zValues.length - 1];
    if (top - bottom < 1.8 || zValues.some((z, i) => i > 0 && z - zValues[i - 1] > 1.5)) continue;
    const [ix, iy] = key.split(":").map(Number);
    const nearby: number[][] = [];
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) nearby.push(...(columns.get(`${ix + dx}:${iy + dy}`) ?? []));
    if (nearby.length < 10) continue;
    const mx = nearby.reduce((sum, p) => sum + p[0], 0) / nearby.length;
    const my = nearby.reduce((sum, p) => sum + p[1], 0) / nearby.length;
    let xx = 0, yy = 0, xy = 0;
    for (const p of nearby) { xx += (p[0] - mx) ** 2; yy += (p[1] - my) ** 2; xy += (p[0] - mx) * (p[1] - my); }
    const spread = Math.sqrt((xx - yy) ** 2 + 4 * xy ** 2);
    const major = (xx + yy + spread) / 2, minor = (xx + yy - spread) / 2;
    if (major / nearby.length < 0.2 || minor / Math.max(major, 1e-6) > 0.1) continue;
    facades.push({
      forward: column.reduce((sum, p) => sum + p[0], 0) / column.length,
      left: column.reduce((sum, p) => sum + p[1], 0) / column.length,
      bottom, height: top - bottom, length: resolution * 1.25,
      yaw: Math.atan2(2 * xy, xx - yy) / 2,
    });
  }
  return { groundHeight, groups, groundVertices, facades };
}
