"use client";

import { CapturePlayback } from "./capture-playback";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { apiJson } from "@/lib/lab-api";

export type ExperimentSpec = {
  source: "carla" | "nuscenes";
  model_ids: string[];
  scene_id: string | null;
  capture_id: string | null;
  native_input_adapter?: "raw" | "intensity_mean_experimental";
  max_latency_ms: number | null;
  scenario: { map: string; weather: string; vehicles: number; pedestrians: number; seed: number; frames: number;
    capture_interval: number; timestep: number; route_spawn_index: number; camera?: { fov: number }; traffic_placement?: "random_spawn" | "nearest_spawn" };
};
type Spec = ExperimentSpec;
type Registry = {
  native_input_adapters?: {id: string; available: boolean; label: string; notice?: string}[];
  models: { id: string; task: string; available: boolean; sources: string[] }[];
  maps: string[]; agent_enabled: boolean; agent_model: string; carla_client_installed: boolean;
};
type Metrics = { class_iou?: {object: number | null}; occupied_iou: number | null; object_recall: number | null; flow_epe_m_s: number | null;
  latency_model_only_ms: { p50: number; p95: number } | null };
type Job = {
  capture_progress?: { completed: number; total: number } | null;
  id: string; status: string; stage: string; error: string | null; spec: { request: Spec };
  result: null | { models: Record<string, { metrics: Metrics; cache_hits: number }>;
    recommendation: { selected: string | null; limitations: string[] };
    manifest: { frames: { id: string; timestamp?: number }[]; native_input_adapter?: {id: string; manifest_sha256?: string; notice?: string} }; limitations: string[] };
};
const weatherLabels: Record<string, string> = { clear: "Quang", fog: "Sương mù", rain: "Mưa" };
const initial: Spec = {
  source: "carla", model_ids: ["occupancy_lidar"], scene_id: null, capture_id: null, max_latency_ms: null,
  scenario: { map: "Town01", weather: "clear", vehicles: 2, pedestrians: 0, seed: 42, frames: 4,
    capture_interval: 0.5, timestep: 0.05, route_spawn_index: 0, traffic_placement: "nearest_spawn" },
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


export function ExperimentWorkspace({ source = "carla", initialSpec, active = true }: { source?: Spec["source"]; initialSpec?: Spec; active?: boolean }) {
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [spec, setSpec] = useState<Spec>(() => initialSpec ?? { ...initial, source, scene_id: source === "nuscenes" ? "scene-0103" : null });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedModel, setSelectedModel] = useState("");

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
    if (!active) return;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await apiJson<{ items: Job[] }>("/api/v1/experiments", controller.signal);
        if (!controller.signal.aborted) setJobs(data.items.filter(job => job.spec.request.source === spec.source));
      } catch (cause) { if (!controller.signal.aborted) setError(String(cause)); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [active, spec.source]);

  useEffect(() => {
    const receive = (event: Event) => {
      setSpec((event as CustomEvent<Spec>).detail); setError("");
    };
    window.addEventListener("p027-agent-plan", receive);
    return () => window.removeEventListener("p027-agent-plan", receive);
  }, []);

  const visibleJobs = jobs.filter(job => job.spec.request.source === spec.source);
  const chosen = visibleJobs.find(job => job.id === selectedId) ?? visibleJobs[0];
  const models = registry?.models.filter(model => model.available && model.sources.includes(spec.source)) ?? [];
  const previewModel = chosen?.spec.request.model_ids.includes(selectedModel) ? selectedModel : chosen?.spec.request.model_ids[0] ?? "";
  const frameCount = chosen?.result?.manifest.frames.length ?? 0;

  const scenario = (key: keyof Spec["scenario"], value: string | number) => setSpec(previous => ({ ...previous, capture_id: null, scenario: { ...previous.scenario, [key]: value } }));

  const submit = async () => {
    setBusy(true); setError("");
    try {
      const body = JSON.stringify(spec);
      if (attempt.current?.body !== body) attempt.current = { body, key: crypto.randomUUID() };
      const job = await post<Job>("", spec, attempt.current.key);
      setSelectedId(job.id);  setJobs(previous => [job, ...previous.filter(item => item.id !== job.id)]);
      attempt.current = null;
    } catch (cause) { setError(String(cause)); }
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
    <PageHeader title="CARLA Experiments" description="Tạo capture, chạy checkpoint thật và so sánh BEV occupancy. Mở bot cạnh workspace để trao đổi và đối chiếu evidence; form này tạo thí nghiệm thủ công." />
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      CARLA dùng occupancy LiDAR; camera giúp đối chiếu bối cảnh, chưa là input của model.
      <details className="mt-2"><summary className="cursor-pointer">Phạm vi môi trường và preset</summary><p className="mt-2">Mưa/sương mù mới đổi RGB, chưa đo độ bền sensor. Bảy checkpoint chạy trên nuScenes; radar CARLA chưa có adapter phù hợp. Preset MVP: Town01, 2 xe, 0 người. Map/traffic khác cần kiểm chứng riêng.</p></details>
      {registry && !registry.carla_client_installed ? <p className="mt-2 font-medium">Backend chưa có CARLA client. Worker cần client/server riêng hoặc dùng nguồn nuScenes.</p> : null}
    </div>
    {error ? <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
    <section className="grid gap-4 rounded-xl border border-[var(--line)] bg-white p-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <Select label="Nguồn dữ liệu" value={spec.source} onChange={event => setSpec(previous => ({ ...previous,
          source: event.target.value as Spec["source"], scene_id: event.target.value === "nuscenes" ? "scene-0103" : null,
          capture_id: null, native_input_adapter: "raw", model_ids: ["occupancy_lidar"], scenario: {...previous.scenario, ...(event.target.value === "nuscenes" ? {traffic_placement: "random_spawn",camera:{fov:90}} : {})} }))}><option value="carla">CARLA</option><option value="nuscenes">nuScenes mini-val</option></Select>
        {spec.source === "carla" ? <>
          <Select label="Map" value={spec.scenario.map} onChange={event => scenario("map", event.target.value)}>{(registry?.maps ?? ["Town01"]).map(map => <option key={map}>{map}</option>)}</Select>
          <Select label="Weather" value={spec.scenario.weather} onChange={event => scenario("weather", event.target.value)}>{["clear", "rain", "fog"].map(weather => <option key={weather}>{weather}</option>)}</Select>
        </> : <Select label="Scene" value={spec.scene_id ?? "scene-0103"} onChange={event => setSpec(previous => ({ ...previous, scene_id: event.target.value }))}>{["scene-0103", "scene-0916"].map(scene => <option key={scene}>{scene}</option>)}</Select>}
      </div>
      <div className="grid gap-3 sm:grid-cols-4">{([ ["frames", "Số frame", 81], ["vehicles", "Xe nền", 40], ["pedestrians", "Người đi bộ", 40], ["seed", "Seed", 2147483647] ] as const)
        .filter(([key]) => spec.source === "carla" || key === "frames").map(([key, label, max]) => <label key={key} className="grid gap-2 text-xs text-[var(--muted)]">{label}<input type="number" min={key === "frames" ? 1 : 0} max={max} value={spec.scenario[key]} onChange={event => scenario(key, Number(event.target.value))} className="rounded-lg border border-[var(--line)] p-3 text-sm" /></label>)}</div>
      {spec.source === "carla" && <div className="grid gap-2 sm:max-w-md">
        <Select label="Góc nhìn camera (FOV)" value={spec.scenario.camera?.fov ?? 90} onChange={event => setSpec(previous => ({ ...previous, capture_id: null, scenario: { ...previous.scenario, camera: { fov: Number(event.target.value) } } }))}>
          <option value={60}>60° · Hẹp / vật phía trước lớn hơn</option>
          <option value={90}>90° · Cân bằng</option>
          <option value={110}>110° · Rộng / bao quát hai bên</option>
        </Select>
        <p className="text-xs text-[var(--muted)]">Áp dụng khi tạo capture mới. FOV hẹp giảm vùng bao quát; occupancy LiDAR hiện không dùng ảnh này để dự đoán.</p>
      </div>}
      {spec.source === "carla" && <Select label="Phân bố xe" value={spec.scenario.traffic_placement ?? "random_spawn"} onChange={event => scenario("traffic_placement", event.target.value)}><option value="nearest_spawn">Spawn gần ego · dễ đối chiếu</option><option value="random_spawn">Spawn ngẫu nhiên theo seed</option></Select>}
      {spec.source === "carla" && <div className="grid gap-2">
        <Select label="Xử lý đầu vào LiDAR" value={spec.native_input_adapter ?? "raw"} onChange={event => setSpec(previous => ({...previous, native_input_adapter: event.target.value as Spec["native_input_adapter"]}))}>
          {(registry?.native_input_adapters ?? [{id:"raw", available:true, label:"Đầu vào gốc"}]).map(adapter => <option key={adapter.id} value={adapter.id} disabled={!adapter.available}>{adapter.label}{!adapter.available ? " · Chưa sẵn sàng" : ""}</option>)}
        </Select>
        {spec.native_input_adapter === "intensity_mean_experimental" && <p className="text-xs text-amber-800">Chỉ căn chỉnh kênh intensity, giữ nguyên checkpoint và dữ liệu gốc. Kiểm chứng còn nhỏ trên Town01; không chứng minh an toàn ngoài thực tế hoặc độ bền thời tiết.</p>}
      </div>}
      <fieldset><legend className="mb-2 text-xs font-semibold">Checkpoint</legend><div className="flex flex-wrap gap-4">{models.map(model => <label key={model.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={spec.model_ids.includes(model.id)} onChange={event => setSpec(previous => ({ ...previous, model_ids: event.target.checked ? [...previous.model_ids, model.id] : previous.model_ids.filter(id => id !== model.id) }))} />{model.id}</label>)}</div></fieldset>
      <div className="flex flex-wrap items-center gap-3"><Button loading={busy} disabled={!spec.model_ids.length} onClick={submit}>Tạo thí nghiệm</Button><Button variant="secondary" onClick={() => window.dispatchEvent(new Event("p027-open-agent"))}>Trao đổi với agent ↗</Button><span className="text-xs text-[var(--muted)]">Agent mở cạnh kết quả, không cần đổi trang.</span></div>
      <details><summary className="cursor-pointer text-xs text-[var(--muted)]">Cấu hình sẽ chạy</summary><pre className="mt-3 overflow-auto text-xs">{JSON.stringify(spec, null, 2)}</pre></details>
    </section>
    <section className="grid gap-4 rounded-xl border border-[var(--line)] bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Thí nghiệm gần đây</h2>{chosen && ["queued", "running"].includes(chosen.status) ? <Button variant="secondary" loading={busy} onClick={cancel}>Hủy job</Button> : null}</div>
      <Select label="Experiment" value={chosen?.id ?? ""} onChange={event => { setSelectedId(event.target.value);  }}>{visibleJobs.map(job => <option key={job.id} value={job.id}>{job.id.slice(0, 8)} · {job.spec.request.source === "carla" ? `${job.spec.request.scenario.map} · ${weatherLabels[job.spec.request.scenario.weather] ?? job.spec.request.scenario.weather} · FOV ${job.spec.request.scenario.camera?.fov ?? 90}°` : job.spec.request.scene_id ?? job.spec.request.source} · {job.result?.manifest.frames.length ?? job.spec.request.scenario.frames} frame · {job.spec.request.native_input_adapter === "intensity_mean_experimental" ? "Căn chỉnh thử nghiệm · " : ""}{job.status}</option>)}</Select>
      {chosen ? <p className="text-sm">Trạng thái: <b>{chosen.status}</b> · {chosen.stage}{chosen.status === "queued" ? " · Chờ worker chạy" : ""}</p> : <p className="text-sm text-[var(--muted)]">Chưa có thí nghiệm.</p>}
      {chosen?.status === "running" && chosen.capture_progress && <div className="grid gap-2">
        <label htmlFor="capture-progress" className="text-xs text-[var(--muted)]">Đã ghi {chosen.capture_progress.completed}/{chosen.capture_progress.total} frame camera + LiDAR. Kết quả model xuất hiện sau inference.</label>
        <progress id="capture-progress" max={chosen.capture_progress.total} value={chosen.capture_progress.completed} className="h-2 w-full accent-[var(--accent)]" />
      </div>}
      {chosen?.status === "running" && chosen.stage === "capture" && !chosen.capture_progress && <p role="status" className="text-xs text-[var(--muted)]">Đang chuẩn bị simulator/cảm biến; chưa có frame đã ghi.</p>}
      {chosen?.error ? <p role="alert" className="text-sm text-red-700">{chosen.error}</p> : null}
      {chosen?.result ? <>
        <p className="text-xs text-[var(--muted)]">Đầu vào: {chosen.result.manifest.native_input_adapter?.id ?? "raw"}{chosen.result.manifest.native_input_adapter?.manifest_sha256 && <span className="ml-2 break-all font-mono">SHA {chosen.result.manifest.native_input_adapter.manifest_sha256}</span>}</p>
        {chosen.spec.request.source === "carla" && frameCount === chosen.spec.request.scenario.frames && registry?.native_input_adapters?.some(adapter => adapter.id === "intensity_mean_experimental" && adapter.available) && <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" onClick={() => {setSpec({...chosen.spec.request, capture_id: chosen.spec.request.capture_id ?? chosen.id, native_input_adapter: chosen.spec.request.native_input_adapter === "intensity_mean_experimental" ? "raw" : "intensity_mean_experimental"}); setError("");}}>Chuẩn bị đối chiếu cùng capture</Button>
          <span className="text-xs text-[var(--muted)]">Giữ camera/reference; đổi xử lý đầu vào. Bấm “Tạo thí nghiệm” để chạy.</span>
        </div>}
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Model", "Occupied IoU", "Object IoU", "Object-cell recall", "Flow EPE (m/s)", "p95 model (ms)", "Cache frames"].map(label => <th key={label} className="border-b p-3">{label}</th>)}</tr></thead><tbody>{Object.entries(chosen.result.models).map(([name, result]) => <tr key={name}><td className="p-3">{name}</td><td>{metric(result.metrics.occupied_iou, true)}</td><td>{metric(result.metrics.class_iou?.object, true)}</td><td>{metric(result.metrics.object_recall, true)}</td><td>{metric(result.metrics.flow_epe_m_s)}</td><td>{metric(result.metrics.latency_model_only_ms?.p95)}</td><td>{result.cache_hits}</td></tr>)}</tbody></table></div>
        {Object.values(chosen.result.models).some(result => result.metrics.object_recall === 0) && <p className="text-sm text-amber-800">Có model object-cell recall bằng 0 trên capture này. Đối chiếu Reference để xem vùng vật thể bị bỏ sót; thứ hạng occupied IoU không chứng minh nhận biết vật thể đáng tin cậy.</p>}
        <p className="text-sm">Đề xuất theo occupied IoU: <b>{chosen.result.recommendation.selected ?? "Chưa có model đáp ứng tiêu chí"}</b></p>
        <details><summary className="cursor-pointer text-xs text-[var(--muted)]">Nguồn đo và giới hạn</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-[var(--muted)]">{[...new Set([...chosen.result.limitations, ...chosen.result.recommendation.limitations])].map(item => <li key={item}>{item}</li>)}</ul></details>
        {frameCount > 0 ? <>
          <div className="grid gap-3 sm:grid-cols-2"><Select label="Model preview" value={previewModel} onChange={event => setSelectedModel(event.target.value)}>{chosen.spec.request.model_ids.map(name => <option key={name}>{name}</option>)}</Select></div>
          <CapturePlayback key={`${chosen.id}:${previewModel}`} job={chosen.id} model={previewModel} count={frameCount} timestamps={chosen.result.manifest.frames.map(frame => frame.timestamp ?? NaN)} interval={chosen.spec.request.scenario.capture_interval} camera={chosen.spec.request.source === "carla"} active={active} />
        </> : null}
      </> : null}
    </section>
  </div>;
}
