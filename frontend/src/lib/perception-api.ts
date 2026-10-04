import { apiJson } from "./lab-api";

export type PerceptionTask = "seg3d" | "occupancy" | "flow";
export type TaskStatus = { id: PerceptionTask | "radar"; frame_count: number; total_frames: number };
export type PerceptionOutput = {
  sample_token: string;
  task: PerceptionTask | "radar";
  model: string;
  source: string;
  sensors: string[];
  limitations?: string[];
  kind?: "prediction" | "ground_truth";
  classes?: { id: number; name: string; color: string }[];
  points?: number[][];
  cells?: number[];
  vectors?: number[][];
};

const cache = new Map<string, Promise<PerceptionOutput>>();
export function loadPerception(token: string, task: PerceptionTask | "radar") {
  const key = `${token}:${task}`;
  if (cache.has(key)) return cache.get(key)!;
  const request = apiJson<PerceptionOutput>(`/api/v1/lab/frames/${encodeURIComponent(token)}/perception/${task}`)
    .catch(error => { cache.delete(key); throw error; });
  cache.set(key, request);
  if (cache.size > 16) cache.delete(cache.keys().next().value!);
  return request;
}

export function clearPerceptionCache() { cache.clear(); }
