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
    void apiJson<{ items: Frame[] }>(`/api/v1/lab/scenes/${encodeURIComponent(scene)}/frames`)
      .then((data) => { setFrames(data.items); setToken(data.items[0]?.sample_token ?? ""); })
      .catch((reason: Error) => setError(reason.message));
  }, [scene]);

  const compare = async () => {
    if (!token || !modelA || !modelB) return;
    setLoading(true); setError("");
    try {
      setResults(await Promise.all([
        apiJson<DetectionFrame>(detectionUrl(token, modelA, threshold)),
        apiJson<DetectionFrame>(detectionUrl(token, modelB, threshold)),
      ]));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể so sánh mô hình"); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!token || !modelA || !modelB) return;
    const controller = new AbortController();
    void Promise.all([
      apiJson<DetectionFrame>(detectionUrl(token, modelA, threshold), controller.signal),
      apiJson<DetectionFrame>(detectionUrl(token, modelB, threshold), controller.signal),
    ]).then(setResults).catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    });
    return () => controller.abort();
  }, [token, modelA, modelB, threshold]);

  const frameA = results[0] ? adaptDetectionFrame(results[0]) : null;
  const frameB = results[1] ? adaptDetectionFrame(results[1]) : null;

  return <div className="grid gap-6">
    <PageHeader title="So sánh mô hình" description="Đối chiếu các model pretrained ổn định trên cùng scene, frame và ngưỡng điểm." actions={<Button loading={loading} onClick={compare}>So sánh lại</Button>} />
    {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
    <section className="grid gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)] md:grid-cols-2 xl:grid-cols-5">
      <Select label="Scene" value={scene} onChange={(e) => setScene(e.target.value)}>{scenes.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}</Select>
      <Select label="Frame" value={token} onChange={(e) => setToken(e.target.value)}>{frames.map((x) => <option key={x.sample_token} value={x.sample_token}>#{x.sample_idx} · {x.timestamp_s.toFixed(2)}s</option>)}</Select>
      <Select label="Mô hình A" value={modelA} onChange={(e) => setModelA(e.target.value)}>{models.map((x) => <option key={x.id} value={x.id}>{modelLabel(x)}</option>)}</Select>
      <Select label="Mô hình B" value={modelB} onChange={(e) => setModelB(e.target.value)}>{models.map((x) => <option key={x.id} value={x.id}>{modelLabel(x)}</option>)}</Select>
      <Select label="Ngưỡng điểm" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))}>{[0.3,0.5,0.7].map((x) => <option key={x} value={x}>{x.toFixed(2)}</option>)}</Select>
    </section>
    <BevModelCompare
      className="shadow-[var(--shadow)]"
      modelA={{ modelId: modelA, modelLabel: modelLabel(modelA), frame: frameA, isLoading: loading, error: error || null }}
      modelB={{ modelId: modelB, modelLabel: modelLabel(modelB), frame: frameB, isLoading: loading, error: error || null }}
      sampleToken={token}
      threshold={threshold}
    />
  </div>;
}
