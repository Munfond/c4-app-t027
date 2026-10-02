export type Scene = { id: string; split: "mini_val"; frame_count: number };
export type Frame = {
  sample_token: string;
  sample_idx: number;
  scene: string;
  timestamp_s: number;
  split: "mini_val";
};
export type ModelInfo = {
  id: string;
  sensors: string[];
  origin: string;
  available: boolean;
  fusion_type: string | null;
};
export type DetectionBox = {
  class_name: string;
  x: number;
  y: number;
  z: number;
  w: number;
  l: number;
  h: number;
  yaw: number;
  vx: number;
  vy: number;
  score: number;
};
export type DetectionFrame = {
  frame: Frame;
  model: string;
  mode: "precomputed";
  coordinates: Record<string, string>;
  boxes: DetectionBox[];
};

export async function apiJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { cache: "no-store", signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `API trả về HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function detectionUrl(token: string, model: string, threshold: number) {
  const query = new URLSearchParams({ model, threshold: String(threshold) });
  return `/api/v1/lab/frames/${encodeURIComponent(token)}/detections?${query}`;
}
