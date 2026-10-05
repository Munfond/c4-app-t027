"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { apiJson } from "@/lib/lab-api";

type Spec = {
  source: "carla" | "nuscenes";
  model_ids: string[];
  scene_id: string | null;
  capture_id: string | null;
  max_latency_ms: number | null;
  scenario: { map: string; weather: string; vehicles: number; pedestrians: number; seed: number; frames: number;
    capture_interval: number; timestep: number; route_spawn_index: number };
};
type Registry = {
  models: { id: string; task: string; available: boolean; sources: string[] }[];
  maps: string[]; agent_enabled: boolean; agent_model: string; carla_client_installed: boolean;
};
type Metrics = { occupied_iou: number | null; object_recall: number | null; flow_epe_m_s: number | null;
  latency_model_only_ms: { p50: number; p95: number } | null };
type Job = {
  id: string; status: string; stage: string; error: string | null; spec: { request: Spec };
  result: null | { models: Record<string, { metrics: Metrics; cache_hits: number }>;
    recommendation: { selected: string | null; limitations: string[] };
    manifest: { frames: { id: string }[] }; limitations: string[] };
};
const initial: Spec = {
  source: "carla", model_ids: ["occupancy_lidar"], scene_id: null, capture_id: null, max_latency_ms: null,
  scenario: { map: "Town03", weather: "clear", vehicles: 8, pedestrians: 8, seed: 42, frames: 4,
    capture_interval: 0.5, timestep: 0.05, route_spawn_index: 0 },
};

async function post<T>(path: string, body: unknown, key?: string): Promise<T> {
  const response = await fetch(`/api/v1/experiments${path}`, {
    method: "POST", headers: { "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data as T;
}

function metric(value: number | null | undefined, percent = false) {
  if (value == null) return "—";
  return percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
}

function OccupancyPreview({ job, model, index }: { job: Job; model: string; index: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const key = `${job.id}:${model}:${index}`;
  const [loaded, setLoaded] = useState<{ key: string; cells: number[] } | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void apiJson<{ cells: number[] }>(`/api/v1/experiments/${job.id}/predictions/${encodeURIComponent(model)}/${index}`, controller.signal)
      .then(data => { if (!controller.signal.aborted) setLoaded({ key, cells: data.cells }); })
      .catch(cause => { if (!controller.signal.aborted) setFailure({ key, message: String(cause) }); });
    return () => controller.abort();
  }, [job.id, model, index, key]);
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, 200, 200);
    if (loaded?.key !== key || loaded.cells.length !== 40000) return;
    const pixels = ctx.createImageData(200, 200);
    const colors = [[16, 38, 46], [80, 167, 152], [255, 177, 76]];
    loaded.cells.forEach((value, cell) => {
      const row = Math.floor(cell / 200), col = cell % 200;
      const offset = ((199 - row) * 200 + 199 - col) * 4;
      const color = colors[value] ?? colors[0];
      pixels.data.set([...color, 255], offset);
    });
    ctx.putImageData(pixels, 0, 0);
  }, [loaded, key]);
  return <div className="grid gap-2">
    <canvas ref={canvas} width={200} height={200} className="aspect-square w-full max-w-[500px] bg-[var(--navy)] [image-rendering:pixelated]" aria-label="Prediction occupancy BEV: forward lên trên, left sang trái" />
    <p className="text-xs text-[var(--muted)]">BEV 2D · 0.5 m/cell · forward ↑ · static xanh · object cam</p>
    {failure?.key === key ? <p role="alert" className="text-sm text-red-700">{failure.message}</p> : null}
  </div>;
}

export function ExperimentWorkspace() {
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [spec, setSpec] = useState<Spec>(initial);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [frameIndex, setFrameIndex] = useState(0);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const attempt = useRef<{ body: string; key: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void apiJson<Registry>("/api/v1/experiments/registry", controller.signal).then(setRegistry)
      .catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await apiJson<{ items: Job[] }>("/api/v1/experiments", controller.signal);
        if (!controller.signal.aborted) setJobs(data.items);
      } catch (cause) { if (!controller.signal.aborted) setError(String(cause)); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);

  const chosen = jobs.find(job => job.id === selectedId) ?? jobs[0];
  const models = registry?.models.filter(model => model.available && model.sources.includes(spec.source)) ?? [];
  const previewModel = chosen?.spec.request.model_ids.includes(selectedModel) ? selectedModel : chosen?.spec.request.model_ids[0] ?? "";
  const frameCount = chosen?.result?.manifest.frames.length ?? 0;
  const previewIndex = Math.min(frameIndex, Math.max(0, frameCount - 1));
  const scenario = (key: keyof Spec["scenario"], value: string | number) => setSpec(previous => ({ ...previous, capture_id: null, scenario: { ...previous.scenario, [key]: value } }));

  const submit = async () => {
    setBusy(true); setError("");
    try {
      const body = JSON.stringify(spec);
      if (attempt.current?.body !== body) attempt.current = { body, key: crypto.randomUUID() };
      const job = await post<Job>("", spec, attempt.current.key);
      setSelectedId(job.id); setFrameIndex(0); setJobs(previous => [job, ...previous.filter(item => item.id !== job.id)]);
      attempt.current = null;
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const draft = async () => {
    setBusy(true); setError("");
    try { setSpec((await post<{ spec: Spec }>("/plan", { message })).spec); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!chosen) return;
    setBusy(true); setError("");
    try {
      const updated = await post<Job>(`/${chosen.id}/cancel`, {});
      setJobs(previous => previous.map(job => job.id === updated.id ? updated : job));
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };

  return <div className="grid gap-6">
    <PageHeader title="CARLA Experiments" description="Tạo capture, chạy checkpoint thật và so sánh BEV occupancy. Agent đề xuất cấu hình; bạn tạo job bằng nút bên dưới." />
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      CARLA hiện hỗ trợ occupancy LiDAR. Bảy checkpoint chạy được trên nuScenes; radar CARLA chưa có adapter RCS/velocity phù hợp.
      Model không dùng camera, nên weather RGB chưa đo được độ bền trước mưa/sương mù.
      {registry && !registry.carla_client_installed ? <p className="mt-2 font-medium">Backend chưa có CARLA client. Worker cần client/server riêng hoặc dùng nguồn nuScenes.</p> : null}
    </div>
    {error ? <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
    <section className="grid gap-4 rounded-xl border border-[var(--line)] bg-white p-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <Select label="Nguồn dữ liệu" value={spec.source} onChange={event => setSpec(previous => ({ ...previous,
          source: event.target.value as Spec["source"], scene_id: event.target.value === "nuscenes" ? "scene-0103" : null,
          capture_id: null, model_ids: ["occupancy_lidar"] }))}><option value="carla">CARLA</option><option value="nuscenes">nuScenes mini-val</option></Select>
        {spec.source === "carla" ? <>
          <Select label="Map" value={spec.scenario.map} onChange={event => scenario("map", event.target.value)}>{(registry?.maps ?? ["Town03"]).map(map => <option key={map}>{map}</option>)}</Select>
          <Select label="Weather" value={spec.scenario.weather} onChange={event => scenario("weather", event.target.value)}>{["clear", "rain", "fog"].map(weather => <option key={weather}>{weather}</option>)}</Select>
        </> : <Select label="Scene" value={spec.scene_id ?? "scene-0103"} onChange={event => setSpec(previous => ({ ...previous, scene_id: event.target.value }))}>{["scene-0103", "scene-0916"].map(scene => <option key={scene}>{scene}</option>)}</Select>}
      </div>
      <div className="grid gap-3 sm:grid-cols-4">{([ ["frames", "Số frame", 81], ["vehicles", "Xe nền", 40], ["pedestrians", "Người đi bộ", 40], ["seed", "Seed", 2147483647] ] as const)
        .filter(([key]) => spec.source === "carla" || key === "frames").map(([key, label, max]) => <label key={key} className="grid gap-2 text-xs text-[var(--muted)]">{label}<input type="number" min={key === "frames" ? 1 : 0} max={max} value={spec.scenario[key]} onChange={event => scenario(key, Number(event.target.value))} className="rounded-lg border border-[var(--line)] p-3 text-sm" /></label>)}</div>
      <fieldset><legend className="mb-2 text-xs font-semibold">Checkpoint</legend><div className="flex flex-wrap gap-4">{models.map(model => <label key={model.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={spec.model_ids.includes(model.id)} onChange={event => setSpec(previous => ({ ...previous, model_ids: event.target.checked ? [...previous.model_ids, model.id] : previous.model_ids.filter(id => id !== model.id) }))} />{model.id}</label>)}</div></fieldset>
      <label className="grid gap-2 text-sm">Yêu cầu cho agent<textarea value={message} maxLength={2000} onChange={event => setMessage(event.target.value)} rows={2} className="rounded-lg border border-[var(--line)] p-3" placeholder="Chạy occupancy LiDAR trên Town03, 4 frame, sương mù, seed 42" /></label>
      <div className="flex flex-wrap items-center gap-3"><Button variant="secondary" loading={busy} disabled={!registry?.agent_enabled || !message.trim()} onClick={draft}>Agent lập cấu hình</Button><Button loading={busy} disabled={!spec.model_ids.length} onClick={submit}>Tạo thí nghiệm</Button><span className="text-xs text-[var(--muted)]">{registry?.agent_enabled ? registry.agent_model : "Agent tắt; form vẫn hoạt động"}</span></div>
      <details><summary className="cursor-pointer text-xs text-[var(--muted)]">Cấu hình sẽ chạy</summary><pre className="mt-3 overflow-auto text-xs">{JSON.stringify(spec, null, 2)}</pre></details>
    </section>
    <section className="grid gap-4 rounded-xl border border-[var(--line)] bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Thí nghiệm gần đây</h2>{chosen && ["queued", "running"].includes(chosen.status) ? <Button variant="secondary" loading={busy} onClick={cancel}>Hủy job</Button> : null}</div>
      <Select label="Experiment" value={chosen?.id ?? ""} onChange={event => { setSelectedId(event.target.value); setFrameIndex(0); }}>{jobs.map(job => <option key={job.id} value={job.id}>{job.id.slice(0, 8)} · {job.spec.request.source} · {job.status}</option>)}</Select>
      {chosen ? <p className="text-sm">Trạng thái: <b>{chosen.status}</b> · {chosen.stage}{chosen.status === "queued" ? " · Chờ worker chạy" : ""}</p> : <p className="text-sm text-[var(--muted)]">Chưa có thí nghiệm.</p>}
      {chosen?.error ? <p role="alert" className="text-sm text-red-700">{chosen.error}</p> : null}
      {chosen?.result ? <>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Model", "Occupied IoU", "Object-cell recall", "Flow EPE (m/s)", "p95 model (ms)", "Cache frames"].map(label => <th key={label} className="border-b p-3">{label}</th>)}</tr></thead><tbody>{Object.entries(chosen.result.models).map(([name, result]) => <tr key={name}><td className="p-3">{name}</td><td>{metric(result.metrics.occupied_iou, true)}</td><td>{metric(result.metrics.object_recall, true)}</td><td>{metric(result.metrics.flow_epe_m_s)}</td><td>{metric(result.metrics.latency_model_only_ms?.p95)}</td><td>{result.cache_hits}</td></tr>)}</tbody></table></div>
        <p className="text-sm">Đề xuất theo occupied IoU: <b>{chosen.result.recommendation.selected ?? "Chưa có model đáp ứng tiêu chí"}</b></p>
        <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--muted)]">{[...chosen.result.limitations, ...chosen.result.recommendation.limitations].map((item, index) => <li key={index}>{item}</li>)}</ul>
        {frameCount > 0 ? <>
          <div className="grid gap-3 sm:grid-cols-2"><Select label="Model preview" value={previewModel} onChange={event => setSelectedModel(event.target.value)}>{chosen.spec.request.model_ids.map(name => <option key={name}>{name}</option>)}</Select><Select label="Frame" value={previewIndex} onChange={event => setFrameIndex(Number(event.target.value))}>{chosen.result.manifest.frames.map((frame, index) => <option key={frame.id} value={index}>{index} · {frame.id}</option>)}</Select></div>
          <div className="grid gap-4 lg:grid-cols-2"><OccupancyPreview job={chosen} model={previewModel} index={previewIndex} />{chosen.spec.request.source === "carla" ? <Image unoptimized width={960} height={540} src={`/api/v1/experiments/${chosen.id}/camera?index=${previewIndex}`} alt="Camera RGB từ capture CARLA, cùng frame prediction" className="h-auto w-full rounded-lg" /> : null}</div>
        </> : null}
      </> : null}
    </section>
  </div>;
}
