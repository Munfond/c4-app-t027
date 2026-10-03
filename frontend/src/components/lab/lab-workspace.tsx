"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CameraPanel } from "@/components/camera";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { BevViewer } from "@/components/viewer";
import { SpatialViewer } from "@/components/viewer/SpatialViewer";
import { apiJson, detectionUrl, modelLabel, mvpModels, type DetectionFrame, type Frame, type ModelInfo, type Scene } from "@/lib/lab-api";
import { adaptDetectionFrame } from "@/lib/viewer";
import { RiskHeatmap } from "./risk-heatmap";
import { SceneTimeline, type PlaybackSpeed } from "./scene-timeline";

export function LabWorkspace() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [scene, setScene] = useState("");
  const [token, setToken] = useState("");
  const [model, setModel] = useState("");
  const [threshold, setThreshold] = useState(0.5);
  const [detections, setDetections] = useState<DetectionFrame | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loadedKey, setLoadedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [spatialMode, setSpatialMode] = useState<"bev" | "3d">("bev");
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [loop, setLoop] = useState(false);
  const [spatialReadyToken, setSpatialReadyToken] = useState<string | null>(null);
  const detectionCache = useRef(new Map<string, DetectionFrame>());

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      apiJson<{ items: Scene[] }>("/api/v1/lab/scenes", controller.signal),
      apiJson<{ items: ModelInfo[] }>("/api/v1/lab/models", controller.signal),
    ]).then(([sceneData, modelData]) => {
      setScenes(sceneData.items);
      const demoModels = mvpModels(modelData.items);
      setModels(demoModels);
      setScene(sceneData.items[0]?.id ?? "");
      setModel(demoModels.find((item) => item.id === "fused")?.id ?? demoModels[0]?.id ?? "");
    }).catch((reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); }).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!scene) return;
    const controller = new AbortController();
    void apiJson<{ items: Frame[] }>(`/api/v1/lab/scenes/${encodeURIComponent(scene)}/frames`, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        const ordered = [...data.items].sort((a, b) => a.timestamp_s - b.timestamp_s);
        setFrames(ordered);
        setToken(ordered[0]?.sample_token ?? "");
      })
      .catch((reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); });
    return () => controller.abort();
  }, [scene]);

  const loadDetections = () => {
    setPlaying(false);
    detectionCache.current.clear();
    setRefresh(value => value + 1);
  };

  useEffect(() => {
    if (!token || !model) return;
    const controller = new AbortController();
    const key = `${token}:${model}:${threshold}:${refresh}`;
    const cached = detectionCache.current.get(key);
    void (cached ? Promise.resolve(cached) : apiJson<DetectionFrame>(detectionUrl(token, model, threshold), controller.signal))
      .then(data => {
        if (controller.signal.aborted) return;
        detectionCache.current.set(key, data);
        while (detectionCache.current.size > 12) detectionCache.current.delete(detectionCache.current.keys().next().value!);
        setDetections(data);
        setLoadedKey(key);
        setError("");
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") { setError(reason.message); setPlaying(false); }
      });
    return () => controller.abort();
  }, [token, model, threshold, refresh]);

  const activeFrame = frames.find((item) => item.sample_token === token);
  const currentIndex = frames.findIndex((item) => item.sample_token === token);
  const nextFrame = currentIndex >= 0 ? frames[currentIndex + 1] : undefined;
  const upcomingFrame = nextFrame ?? (loop && frames.length > 1 ? frames[0] : undefined);
  const ready = loadedKey === `${token}:${model}:${threshold}:${refresh}` && activeFrame?.scene === scene;
  const viewerFrame = useMemo(() => detections && ready ? adaptDetectionFrame(detections) : null, [detections, ready]);
  const readyForPlayback = ready && (spatialMode !== "3d" || spatialReadyToken === token);

  useEffect(() => {
    if (!playing || !readyForPlayback || currentIndex < 0) return;
    const atEnd = currentIndex === frames.length - 1;
    const intervalSeconds = atEnd ? 0.5 : frames[currentIndex + 1].timestamp_s - frames[currentIndex].timestamp_s;
    const delay = Math.max(120, Math.min(2000, intervalSeconds * 1000 / speed));
    const timer = window.setTimeout(() => {
      if (atEnd && !loop) setPlaying(false);
      else setToken(frames[atEnd ? 0 : currentIndex + 1].sample_token);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [playing, readyForPlayback, currentIndex, frames, speed, loop]);

  useEffect(() => {
    const pauseWhenHidden = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener("visibilitychange", pauseWhenHidden);
    return () => document.removeEventListener("visibilitychange", pauseWhenHidden);
  }, []);

  useEffect(() => {
    if (!playing || !ready || !upcomingFrame) return;
    const key = `${upcomingFrame.sample_token}:${model}:${threshold}:${refresh}`;
    if (detectionCache.current.has(key)) return;
    const controller = new AbortController();
    void apiJson<DetectionFrame>(detectionUrl(upcomingFrame.sample_token, model, threshold), controller.signal)
      .then(data => { if (!controller.signal.aborted) detectionCache.current.set(key, data); })
      .catch(() => { /* Current-frame request reports errors; prefetch is optional. */ });
    return () => controller.abort();
  }, [playing, ready, upcomingFrame, model, threshold, refresh]);

  const seek = (index: number) => {
    const selected = frames[index];
    if (!selected) return;
    setPlaying(false);
    setToken(selected.sample_token);
  };

  const togglePlayback = () => {
    if (playing) { setPlaying(false); return; }
    if (currentIndex === frames.length - 1 && frames.length > 1) setToken(frames[0].sample_token);
    setPlaying(true);
  };
  const stopOnSpatialError = useCallback(() => setPlaying(false), []);
  return <div className="grid gap-6">
    <PageHeader title="Perception Lab" description="Trực quan hóa kết quả tính sẵn từ các model pretrained trên nuScenes mini; model tự train được dành cho giai đoạn tối ưu sau MVP." actions={<Button loading={loading || (!ready && !error)} onClick={loadDetections}>Tải lại kết quả</Button>} />
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><b>Chế độ MVP ổn định:</b> dùng prediction precomputed, không chạy inference nặng trên VPS. Mini scenes có mặt trong tập train official nên kết quả dùng để trực quan hóa, không phải so sánh benchmark công bằng.</div>
    {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
    <section className="grid gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)] sm:grid-cols-2 xl:grid-cols-4">
      <Select label="Scene" value={scene} onChange={(e) => { setPlaying(false); setFrames([]); setToken(""); setScene(e.target.value); }} disabled={!scenes.length}>{scenes.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.frame_count} frames</option>)}</Select>
      <Select label="Frame" value={token} onChange={(e) => seek(frames.findIndex(item => item.sample_token === e.target.value))} disabled={!frames.length || activeFrame?.scene !== scene}>{frames.map((x) => <option key={x.sample_token} value={x.sample_token}>#{x.sample_idx} · +{(x.timestamp_s - frames[0].timestamp_s).toFixed(1)}s</option>)}</Select>
      <Select label="Mô hình" value={model} onChange={(e) => { setPlaying(false); setModel(e.target.value); }} disabled={!models.length}>{models.map((x) => <option key={x.id} value={x.id}>{modelLabel(x)}</option>)}</Select>
      <Select label="Ngưỡng điểm" value={threshold} onChange={(e) => { setPlaying(false); setThreshold(Number(e.target.value)); }}>{[0.3,0.5,0.7].map((x) => <option key={x} value={x}>{x.toFixed(2)}</option>)}</Select>
    </section>
    <section className="min-h-[560px] overflow-hidden rounded-[var(--radius)] border border-[#173941] bg-zinc-950 shadow-[var(--shadow)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-[#0b2028] px-4 py-3 text-xs text-[#b4cdd2]">
        <div className="flex items-center gap-3"><b className="text-white">Không gian quanh xe</b><div className="flex rounded-lg border border-white/10 bg-black/20 p-0.5" role="group" aria-label="Chế độ bản đồ">
          <button type="button" aria-pressed={spatialMode === "bev"} onClick={() => setSpatialMode("bev")} className={`rounded-md px-3 py-1.5 ${spatialMode === "bev" ? "bg-teal-400 font-semibold text-[#08252a]" : "text-slate-300 hover:bg-white/10"}`}>BEV 2D</button>
          <button type="button" aria-pressed={spatialMode === "3d"} onClick={() => { setSpatialReadyToken(null); setSpatialMode("3d"); }} className={`rounded-md px-3 py-1.5 ${spatialMode === "3d" ? "bg-teal-400 font-semibold text-[#08252a]" : "text-slate-300 hover:bg-white/10"}`}>Bản đồ 3D</button>
        </div></div><span>{activeFrame?.scene === scene ? `${activeFrame.scene} · #${activeFrame.sample_idx}` : "Chưa có frame"}</span>
      </div>
      <SceneTimeline frames={frames} currentIndex={currentIndex} playing={playing} speed={speed} loop={loop} waiting={playing && !readyForPlayback} onSeek={seek} onTogglePlay={togglePlayback} onSpeedChange={setSpeed} onLoopChange={setLoop} />
      <div className="h-[520px]">{spatialMode === "3d" ? <SpatialViewer frame={viewerFrame} sampleToken={activeFrame?.scene === scene ? token : null} nextToken={playing ? upcomingFrame?.sample_token : undefined} requestError={error || null} onFrameReady={setSpatialReadyToken} onFrameError={stopOnSpatialError} /> : <BevViewer error={error || null} frame={viewerFrame} isLoading={loading || (!ready && !error)} />}</div>
    </section>
    {token && activeFrame?.scene === scene ? <RiskHeatmap sampleToken={token} /> : null}
    {token && activeFrame?.scene === scene ? <CameraPanel sampleToken={token} /> : null}
  </div>;
}
