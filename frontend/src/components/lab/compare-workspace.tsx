"use client";

import { useEffect, useState } from "react";
import { DetectionSummary } from "./detection-summary";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { apiJson, detectionUrl, type DetectionFrame, type Frame, type ModelInfo, type Scene } from "@/lib/lab-api";

export function CompareWorkspace() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [scene, setScene] = useState("");
  const [token, setToken] = useState("");
  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");
  const [results, setResults] = useState<[DetectionFrame | null, DetectionFrame | null]>([null, null]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void Promise.all([
      apiJson<{ items: Scene[] }>("/api/v1/lab/scenes"),
      apiJson<{ items: ModelInfo[] }>("/api/v1/lab/models"),
    ]).then(([sceneData, modelData]) => {
      const available = modelData.items.filter((item) => item.available);
      setScenes(sceneData.items); setModels(available);
      setScene(sceneData.items[0]?.id ?? "");
      setModelA(available[0]?.id ?? ""); setModelB(available[1]?.id ?? available[0]?.id ?? "");
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
        apiJson<DetectionFrame>(detectionUrl(token, modelA, 0.3)),
        apiJson<DetectionFrame>(detectionUrl(token, modelB, 0.3)),
      ]));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể so sánh mô hình"); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!token || !modelA || !modelB) return;
    const controller = new AbortController();
    void Promise.all([
      apiJson<DetectionFrame>(detectionUrl(token, modelA, 0.3), controller.signal),
      apiJson<DetectionFrame>(detectionUrl(token, modelB, 0.3), controller.signal),
    ]).then(setResults).catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    });
    return () => controller.abort();
  }, [token, modelA, modelB]);

  return <div className="grid gap-6">
    <PageHeader title="So sánh mô hình" description="Đối chiếu hai kết quả precomputed trên cùng scene và frame." actions={<Button loading={loading} onClick={compare}>So sánh lại</Button>} />
    {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
    <section className="grid gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)] md:grid-cols-4">
      <Select label="Scene" value={scene} onChange={(e) => setScene(e.target.value)}>{scenes.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}</Select>
      <Select label="Frame" value={token} onChange={(e) => setToken(e.target.value)}>{frames.map((x) => <option key={x.sample_token} value={x.sample_token}>#{x.sample_idx} · {x.timestamp_s.toFixed(2)}s</option>)}</Select>
      <Select label="Mô hình A" value={modelA} onChange={(e) => setModelA(e.target.value)}>{models.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}</Select>
      <Select label="Mô hình B" value={modelB} onChange={(e) => setModelB(e.target.value)}>{models.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}</Select>
    </section>
    <div className="grid gap-5 xl:grid-cols-2">
      {[modelA, modelB].map((model, index) => <section className="viewer-grid relative min-h-[440px] overflow-hidden rounded-[var(--radius)] border border-[#173941] shadow-[var(--shadow)]" key={`${index}-${model}`}>
        <div className="absolute inset-x-0 top-0 z-10 flex justify-between border-b border-white/10 bg-[#0b2028cc] px-4 py-3 text-xs text-[#b4cdd2]"><span>Mô hình {index ? "B" : "A"}</span><b className="text-white">{model || "—"}</b></div>
        <DetectionSummary data={results[index]} />
      </section>)}
    </div>
  </div>;
}
