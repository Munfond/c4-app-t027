"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { BevModelCompare } from "@/components/viewer";
import { apiJson, detectionUrl, modelLabel, mvpModels, type DetectionFrame, type Frame, type ModelInfo, type Scene } from "@/lib/lab-api";
import { adaptDetectionFrame } from "@/lib/viewer";

export function CompareWorkspace() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [scene, setScene] = useState("");
  const [token, setToken] = useState("");
  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");
  const [threshold, setThreshold] = useState(0.5);
  const [results, setResults] = useState<[DetectionFrame | null, DetectionFrame | null]>([null, null]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loadedKey, setLoadedKey] = useState("");

  useEffect(() => {
    void Promise.all([
      apiJson<{ items: Scene[] }>("/api/v1/lab/scenes"),
      apiJson<{ items: ModelInfo[] }>("/api/v1/lab/models"),
    ]).then(([sceneData, modelData]) => {
      const available = mvpModels(modelData.items);
      setScenes(sceneData.items); setModels(available);
      setScene(sceneData.items[0]?.id ?? "");
      setModelA(available.find((item) => item.id === "official_cl")?.id ?? available[0]?.id ?? "");
      setModelB(available.find((item) => item.id === "fused")?.id ?? available[1]?.id ?? available[0]?.id ?? "");
    }).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
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

  useEffect(() => {
    if (!token || !modelA || !modelB) return;
    const controller = new AbortController();
    const key = `${token}:${modelA}:${modelB}:${threshold}:${refresh}`;
    void Promise.all([
      apiJson<DetectionFrame>(detectionUrl(token, modelA, threshold), controller.signal),
      apiJson<DetectionFrame>(detectionUrl(token, modelB, threshold), controller.signal),
    ]).then((data) => {
      if (controller.signal.aborted) return;
      setResults(data);
      setLoadedKey(key);
    }).catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    });
    return () => controller.abort();
  }, [token, modelA, modelB, threshold, refresh]);

  const ready = loadedKey === `${token}:${modelA}:${modelB}:${threshold}:${refresh}` && frames.some((frame) => frame.sample_token === token && frame.scene === scene);
  const frameA = ready && results[0] ? adaptDetectionFrame(results[0]) : null;
  const frameB = ready && results[1] ? adaptDetectionFrame(results[1]) : null;

  return <div className="comparison-workspace">
    <PageHeader eyebrow="02 / MODEL COMPARISON" title="Hai mô hình. Một góc nhìn." description="Cùng frame, cùng ngưỡng điểm, cùng hệ tọa độ. Kéo hoặc phóng to một bản đồ để quan sát cả hai mô hình trong cùng một không gian." actions={<Button variant="secondary" loading={loading || (!ready && !error)} onClick={() => { setError(""); setRefresh(value => value + 1); }}>Tải lại so sánh ↗</Button>} />
    {error ? <div role="alert" className="border-l-2 border-red-600 bg-red-50 px-4 py-3 text-sm text-red-800">Không thể tải dữ liệu: {error}</div> : null}
    <section aria-label="Thiết lập so sánh" className="comparison-controls">
      <div className="comparison-shared">
        <p className="eyebrow">ĐIỀU KIỆN CHUNG</p>
        <Select label="Scene" value={scene} disabled={!scenes.length} onChange={(e) => { setError(""); setFrames([]); setToken(""); setScene(e.target.value); }}>{scenes.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}</Select>
        <Select label="Frame" value={token} disabled={!frames.length} onChange={(e) => { setError(""); setToken(e.target.value); }}>{frames.map((x) => <option key={x.sample_token} value={x.sample_token}>#{x.sample_idx} · +{(x.timestamp_s - frames[0].timestamp_s).toFixed(1)}s</option>)}</Select>
        <Select label="Ngưỡng điểm" value={threshold} onChange={(e) => { setError(""); setThreshold(Number(e.target.value)); }}>{[0.3,0.5,0.7].map((x) => <option key={x} value={x}>{x.toFixed(2)}</option>)}</Select>
      </div>
      <div className="comparison-models">
        <div><span className="comparison-letter" aria-hidden="true">A</span><div className="comparison-model-copy"><Select label="Mô hình A" value={modelA} disabled={!models.length} onChange={(e) => { setError(""); setModelA(e.target.value); }}>{models.map((x) => <option key={x.id} value={x.id}>{modelLabel(x).split(" · ")[0]}</option>)}</Select><p>{modelLabel(modelA).split(" · ")[1]}</p></div></div>
        <div><span className="comparison-letter" aria-hidden="true">B</span><div className="comparison-model-copy"><Select label="Mô hình B" value={modelB} disabled={!models.length} onChange={(e) => { setError(""); setModelB(e.target.value); }}>{models.map((x) => <option key={x.id} value={x.id}>{modelLabel(x).split(" · ")[0]}</option>)}</Select><p>{modelLabel(modelB).split(" · ")[1]}</p></div></div>
      </div>
    </section>
    <BevModelCompare
      modelA={{ modelId: modelA, modelLabel: modelLabel(modelA), frame: frameA, isLoading: loading || (!ready && !error), error: error || null }}
      modelB={{ modelId: modelB, modelLabel: modelLabel(modelB), frame: frameB, isLoading: loading || (!ready && !error), error: error || null }}
      sampleToken={token}
      threshold={threshold}
    />
    <p className="comparison-footnote"><span>ĐỒNG BỘ GÓC NHÌN</span>Đây là đối chiếu trực quan trên cùng frame. Checkpoint official có thể đã thấy mini-val khi huấn luyện; xem Benchmarks để đọc giới hạn trước khi kết luận mô hình nào tốt hơn.</p>
  </div>;
}
