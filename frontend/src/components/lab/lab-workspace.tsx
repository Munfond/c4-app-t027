"use client";

import { useEffect, useState } from "react";
import { CameraPanel } from "@/components/camera";
import { DetectionSummary } from "./detection-summary";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { apiJson, detectionUrl, type DetectionFrame, type Frame, type ModelInfo, type Scene } from "@/lib/lab-api";

export function LabWorkspace() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [scene, setScene] = useState("");
  const [token, setToken] = useState("");
  const [model, setModel] = useState("");
  const [threshold, setThreshold] = useState(0.3);
  const [detections, setDetections] = useState<DetectionFrame | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      apiJson<{ items: Scene[] }>("/api/v1/lab/scenes", controller.signal),
      apiJson<{ items: ModelInfo[] }>("/api/v1/lab/models", controller.signal),
    ]).then(([sceneData, modelData]) => {
      setScenes(sceneData.items);
      setModels(modelData.items.filter((item) => item.available));
      setScene(sceneData.items[0]?.id ?? "");
      setModel(modelData.items.find((item) => item.available)?.id ?? "");
    }).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!scene) return;
    const controller = new AbortController();
    void apiJson<{ items: Frame[] }>(`/api/v1/lab/scenes/${encodeURIComponent(scene)}/frames`, controller.signal)
      .then((data) => { setFrames(data.items); setToken(data.items[0]?.sample_token ?? ""); })
      .catch((reason: Error) => setError(reason.message));
    return () => controller.abort();
  }, [scene]);

  const loadDetections = async () => {
    if (!token || !model) return;
    setLoading(true); setError("");
    try { setDetections(await apiJson<DetectionFrame>(detectionUrl(token, model, threshold))); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể tải detection"); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!token || !model) return;
    const controller = new AbortController();
    void apiJson<DetectionFrame>(detectionUrl(token, model, threshold), controller.signal)
      .then(setDetections)
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, [token, model, threshold]);

  const activeFrame = frames.find((item) => item.sample_token === token);
  return <div className="grid gap-6">
    <PageHeader title="Perception Lab" description="Khám phá dữ liệu nuScenes mini, detection và camera đã ẩn danh từ API." actions={<Button loading={loading} onClick={loadDetections}>Tải lại kết quả</Button>} />
    {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
    <section className="grid gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)] sm:grid-cols-2 xl:grid-cols-4">
      <Select label="Scene" value={scene} onChange={(e) => setScene(e.target.value)} disabled={!scenes.length}>{scenes.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.frame_count} frames</option>)}</Select>
      <Select label="Frame" value={token} onChange={(e) => setToken(e.target.value)} disabled={!frames.length}>{frames.map((x) => <option key={x.sample_token} value={x.sample_token}>#{x.sample_idx} · {x.timestamp_s.toFixed(2)}s</option>)}</Select>
      <Select label="Mô hình" value={model} onChange={(e) => setModel(e.target.value)} disabled={!models.length}>{models.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.sensors.join("+")}</option>)}</Select>
      <Select label="Ngưỡng điểm" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))}>{[0.3,0.5,0.7].map((x) => <option key={x} value={x}>{x.toFixed(2)}</option>)}</Select>
    </section>
    <section className="viewer-grid relative min-h-[430px] overflow-hidden rounded-[var(--radius)] border border-[#173941] shadow-[var(--shadow)]">
      <div className="absolute inset-x-0 top-0 z-10 flex justify-between border-b border-white/10 bg-[#0b2028cc] px-4 py-3 text-xs text-[#b4cdd2]"><b className="text-white">Detection frame</b><span>{activeFrame ? `${activeFrame.scene} · #${activeFrame.sample_idx}` : "Chưa có frame"}</span></div>
      <DetectionSummary data={detections} />
    </section>
    {token ? <CameraPanel sampleToken={token} /> : null}
  </div>;
}
