import type { DetectionFrame } from "@/lib/lab-api";

export type EnvironmentFrame = {
  points: number[][];
  source: string;
  radius_m: number;
  voxel_m: number;
};

class FrameCache<T> {
  private readonly entries = new Map<string, Promise<T>>();

  constructor(private readonly capacity: number) {}

  get(key: string, load: () => Promise<T>): Promise<T> {
    const existing = this.entries.get(key);
    if (existing) {
      this.entries.delete(key);
      this.entries.set(key, existing);
      return existing;
    }

    const request = load().catch((error: unknown) => {
      if (this.entries.get(key) === request) this.entries.delete(key);
      throw error;
    });
    this.entries.set(key, request);
    while (this.entries.size > this.capacity) {
      this.entries.delete(this.entries.keys().next().value!);
    }
    return request;
  }

  clear(): void {
    this.entries.clear();
  }
}

export const detectionFrames = new FrameCache<DetectionFrame>(16);
export const environmentFrames = new FrameCache<EnvironmentFrame>(12);

export function loadEnvironmentFrame(token: string): Promise<EnvironmentFrame> {
  return environmentFrames.get(token, async () => {
    const response = await fetch(`/api/v1/lab/frames/${encodeURIComponent(token)}/environment`);
    if (!response.ok) throw new Error(`LiDAR chưa sẵn sàng (HTTP ${response.status})`);
    return response.json() as Promise<EnvironmentFrame>;
  });
}
