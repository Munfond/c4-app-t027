"use client";

import { useEffect, useMemo, useState } from "react";
import { loadEnvironmentFrame, type EnvironmentFrame } from "@/lib/lab-frame-cache";
import { loadPerception, type PerceptionOutput } from "@/lib/perception-api";
import { PointCloudCanvas } from "@/components/viewer/PointCloudCanvas";

export function SensorWorkspace({ token, lidar, radar, onReady }: { token: string; lidar: boolean; radar: boolean; onReady: (token: string) => void }) {
  const [result, setResult] = useState<{ token: string; lidar?: EnvironmentFrame; radar?: PerceptionOutput; lidarError?: string; radarError?: string } | null>(null);
  useEffect(() => {
    let active = true;
    void Promise.allSettled([loadEnvironmentFrame(token), loadPerception(token, "radar")]).then(([l, r]) => {
      if (active) setResult({ token,
        ...(l.status === "fulfilled" ? { lidar: l.value } : { lidarError: "LiDAR của frame này chưa sẵn sàng." }),
        ...(r.status === "fulfilled" ? { radar: r.value } : { radarError: "Chưa có bản xuất Radar của frame này." }),
      });
    });
    return () => { active = false; };
  }, [token]);
  const current = result?.token === token ? result : null;
  const layers = useMemo(() => [
    { id: "lidar", name: "LiDAR", color: "#8dc7c4", points: current?.lidar?.points ?? [], visible: lidar, size: .14 },
    { id: "radar", name: "Radar", color: "#ffbb72", points: current?.radar?.points ?? [], visible: radar, size: .65 },
  ], [current, lidar, radar]);
  return <div className="sensor-workspace">
    <PointCloudCanvas layers={layers} token={current ? token : ""} onReady={current ? onReady : undefined} />
    {!current ? <div role="status" className="stage-message">Đang đồng bộ LiDAR và Radar…</div> : null}
    {current?.lidarError || current?.radarError ? <p role="status" className="sensor-warning">{[current.lidarError, current.radarError].filter(Boolean).join(" ")}</p> : null}
    {!lidar && !radar ? <div className="sensor-empty" role="status">Đã ẩn cả hai lớp. Bật LiDAR hoặc Radar để tiếp tục quan sát.</div> : null}
  </div>;
}
