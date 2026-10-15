"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { apiJson } from "@/lib/lab-api";

type Lidar = { channels: number; points_per_second: number; range_m: number };
type Scenario = { map: string; weather: string; vehicles: number; frames: number; lidar: Lidar };
type Trial = { id: string; environment: number; profile: string; status: string; stage: string; error: string | null;
  result: null | { manifest: { frames: { id: string }[] } } };
type Row = { job_id: string; profile: string; status: string; error: string | null; occupied_iou: number | null;
  iou_drop: number | null; reference_matches_baseline: boolean; lidar_bytes_per_second: number | null;
  data_reduction_fraction: number | null; latency_model_only_ms: { p50: number; p95: number } | null };
type Comparison = { environments: { environment: number; scenario: Scenario; trials: Row[]; provisional_selected: string | null }[] };
type Summary = { explanation: string; comparison: Comparison };
type Study = { id: string; status: string; total_trials: number; jobs: Trial[]; metadata: { request?: string; model?: string };
  spec: { scenarios: Scenario[]; profiles: { name: string; lidar: Lidar }[]; max_iou_drop: number }; summary: Summary | null };
type Registry = { agent_enabled: boolean; agent_model: string; carla_client_installed: boolean };
const base = "/api/v1/experiments";
const examples = [
  "Tìm mức dữ liệu LiDAR thấp nhất mà model vẫn đạt chất lượng, so sánh các mức trung gian từ 300000 đến 600000 điểm/giây.",
  "Tôi muốn tạo xe chạy trên đường cao tốc với nhiều xe và thay đổi làn liên tục. Tìm cấu hình LiDAR tiết kiệm dữ liệu.",
  "So sánh cấu hình LiDAR trong Town01 trời quang, mưa và sương mù, giữ nguyên FOV và vị trí lắp.",
];
async function post<T>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(base + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data as T;
}
function number(value: number | null | undefined, digits = 4) { return value == null ? "—" : value.toFixed(digits); }
function status(value: string) {
  return ({ queued: "Chờ worker", running: "Đang chạy", succeeded: "Hoàn tất", failed: "Lỗi", completed: "Hoàn tất", cancelled: "Đã dừng" } as Record<string, string>)[value] ?? value;
}

function OutputPreview({ job, frame }: { job: string; frame: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const ctx = canvas.current?.getContext("2d");
    ctx?.clearRect(0, 0, 200, 200);
    void apiJson<{ cells: number[]; shape: number[] }>(`${base}/${job}/predictions/occupancy_lidar/${frame}`, controller.signal)
      .then(data => {
        if (controller.signal.aborted || !ctx) return;
        if (data.cells.length !== 40000 || data.shape.join() !== "200,200") throw new Error("Output có kích thước không hợp lệ");
        setError("");
        const pixels = ctx.createImageData(200, 200);
        const colors = [[16, 38, 46], [80, 167, 152], [255, 177, 76]];
        data.cells.forEach((cell, i) => pixels.data.set([...(colors[cell] ?? colors[0]), 255], (39999 - i) * 4));
        ctx.putImageData(pixels, 0, 0);
      }).catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, [job, frame]);
  return <div><canvas ref={canvas} width={200} height={200} className="aspect-square w-full max-w-80 rounded-lg bg-[var(--navy)] [image-rendering:pixelated]" aria-label="Output occupancy: xanh là static, cam là object" /><p className="mt-2 text-xs text-[var(--muted)]">Checkpoint output · static xanh · object cam · forward ↑</p>{error && <p role="alert">{error}</p>}</div>;
}

export function SensorAgentWorkspace() {
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [history, setHistory] = useState<Study[]>([]);
  const [study, setStudy] = useState<Study | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [message, setMessage] = useState("");
  const [drop, setDrop] = useState("0.02");
  const [frames, setFrames] = useState("20");
  const [busy, setBusy] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [error, setError] = useState("");
  const [selectedJob, setSelectedJob] = useState("");
  const [frame, setFrame] = useState(0);
  const [tick, setTick] = useState(0);
  const summaryAttempts = useRef(new Set<string>());
  const currentId = useRef("");
  const ident = study?.id;

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      apiJson<Registry>(`${base}/registry`, controller.signal),
      apiJson<{ items: Study[] }>(`${base}/sensor-agent`, controller.signal),
    ]).then(([config, data]) => {
      if (controller.signal.aborted) return;
      setRegistry(config); setHistory(data.items);
      const running = data.items.find(item => item.status === "running");
      if (running) { currentId.current = running.id; setStudy(running); }
    }).catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!ident) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const fresh = await apiJson<Study>(`${base}/sensor-agent/${ident}`, controller.signal);
        if (controller.signal.aborted) return;
        setStudy(fresh);
        setHistory(previous => [fresh, ...previous.filter(item => item.id !== fresh.id)]);
        if (fresh.status === "completed") {
          const report = await apiJson<Comparison>(`${base}/sensor-agent/${ident}/comparison`, controller.signal);
          if (!controller.signal.aborted) setComparison(report);
          if (!controller.signal.aborted && !fresh.summary && !summaryAttempts.current.has(ident)) {
            summaryAttempts.current.add(ident);
            setExplaining(true);
            try {
              const summary = await post<Summary>(`/sensor-agent/${ident}/summarize`);
              if (!controller.signal.aborted) setStudy({ ...fresh, summary });
            } catch (cause) {
              if (!controller.signal.aborted) setError(String(cause));
            } finally { setExplaining(false); }
          }
        }
        if (fresh.status === "running") timer = setTimeout(poll, 2500);
      } catch (cause) {
        if (!controller.signal.aborted) { setError(String(cause)); timer = setTimeout(poll, 5000); }
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [ident, tick]);

  const choose = (item: Study) => {
    currentId.current = item.id; setStudy(item); setComparison(item.summary?.comparison ?? null);
    setSelectedJob(""); setFrame(0); setError(""); setTick(previous => previous + 1);
  };
  const send = async () => {
    setBusy(true); setError("");
    try {
      const item = await post<Study>("/sensor-agent/start", { message: message.trim(), max_iou_drop: Number(drop), frames: Number(frames) });
      choose(item); setMessage(""); setHistory(previous => [item, ...previous]);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!study) return;
    setBusy(true);
    try { choose(await post<Study>(`/sensor-agent/${study.id}/cancel`)); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const explain = async () => {
    if (!study) return;
    const id = study.id;
    setExplaining(true); setError("");
    try {
      const summary = await post<Summary>(`/sensor-agent/${id}/summarize`);
      if (currentId.current === id) setStudy(previous => previous?.id === id ? { ...previous, summary } : previous);
    } catch (cause) { setError(String(cause)); }
    finally { setExplaining(false); }
  };
  const done = study?.jobs.filter(job => ["succeeded", "failed", "cancelled"].includes(job.status)).length ?? 0;
  const active = study?.jobs.find(job => ["queued", "running"].includes(job.status));
  const completedJobs = study?.jobs.filter(job => job.status === "succeeded") ?? [];
  const preview = completedJobs.find(job => job.id === selectedJob) ?? completedJobs[0];
  const previewFrame = Math.min(frame, Math.max(0, (preview?.result?.manifest.frames.length ?? 1) - 1));
  const running = history.some(item => item.status === "running");
  const controlsValid = Number.isFinite(Number(drop)) && Number(drop) >= 0 && Number(drop) <= 0.2 && Number.isInteger(Number(frames)) && Number(frames) >= 2 && Number(frames) <= 20;
  const panel = "rounded-2xl border border-[var(--line)] bg-white p-5";

  return <div className="mx-auto grid max-w-[1500px] gap-6 py-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-xs font-semibold tracking-[0.2em] text-[var(--accent)]">PROMPT → CARLA → CHECKPOINT → METRICS</p><h1 className="text-3xl font-semibold">Sensor Agent</h1><p className="mt-2 text-sm text-[var(--muted)]">Tìm cấu hình LiDAR ít dữ liệu hơn, với chất lượng bạn chấp nhận.</p></div><span className="rounded-full bg-[var(--accent-soft)] px-4 py-2 text-sm">{registry?.agent_model ?? "Đang kết nối agent…"}</span></header>
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}<button className="ml-4 underline" onClick={() => { setError(""); setTick(value => value + 1); }}>Kiểm tra lại kết nối</button></div>}
    {registry && (!registry.agent_enabled || !registry.carla_client_installed) && <p role="status" className="rounded-xl bg-amber-50 p-4 text-sm">{!registry.agent_enabled ? "Agent chưa bật hoặc chưa có API key ở backend. " : ""}{!registry.carla_client_installed ? "Chưa tìm thấy CARLA client. " : ""}Kiểm tra cấu hình server trước khi gửi yêu cầu.</p>}
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(320px,0.85fr)_minmax(0,1.5fr)]">
      <section className={`${panel} grid gap-5`} aria-label="Chat với sensor agent">
        <div className="flex items-center justify-between"><h2 className="font-semibold">Trao đổi với agent</h2><span className="text-xs text-[var(--muted)]">occupancy_lidar</span></div>
        <div className="rounded-xl bg-[var(--surface-subtle)] p-4 text-sm leading-6">Mô tả cảnh và mục tiêu. Tôi sẽ đề xuất cấu hình LiDAR, chạy baseline cùng các cấu hình thử, rồi so sánh occupied IoU và lượng dữ liệu.</div>
        {study && <div className="grid gap-3" aria-live="polite"><div className="ml-5 rounded-xl bg-[var(--navy)] p-4 text-sm leading-6 text-white">{study.metadata.request ?? "Study cảm biến"}</div><div className="rounded-xl border border-[var(--line)] p-4 text-sm leading-6">{study.spec.scenarios.map((scene, i) => <p key={i}>{scene.map} · {scene.weather} · {scene.vehicles} xe · {scene.frames} frame/cấu hình</p>)}<p className="mt-2">Baseline + {study.spec.profiles.length} cấu hình thử. Giảm IoU tối đa <strong>{study.spec.max_iou_drop.toFixed(3)}</strong>.</p>{study.summary && <p className="mt-3 whitespace-pre-wrap border-t border-[var(--line)] pt-3">{study.summary.explanation}</p>}{explaining && <p className="mt-3 text-[var(--muted)]">Agent đang đọc metric và giải thích…</p>}</div></div>}
        <form className="grid gap-3" onSubmit={event => { event.preventDefault(); void send(); }}>
          <label className="text-sm font-medium" htmlFor="agent-message">Yêu cầu của bạn</label>
          <textarea id="agent-message" value={message} onChange={event => setMessage(event.target.value)} maxLength={2000} rows={5} placeholder="Tìm mức dữ liệu LiDAR thấp nhất mà model vẫn đạt chất lượng trong cảnh cao tốc nhiều xe…" className="w-full resize-y rounded-xl border border-[var(--line)] p-3 text-sm leading-6" />
          <div className="grid grid-cols-2 gap-3"><label className="grid gap-2 text-xs">Giảm IoU tối đa (tuyệt đối)<input aria-label="Giảm IoU tối đa" type="number" min={0} max={0.2} step={0.005} required value={drop} onChange={event => setDrop(event.target.value)} className="rounded-lg border border-[var(--line)] p-2 text-sm" /></label><label className="grid gap-2 text-xs">Frame mỗi cấu hình<input aria-label="Frame mỗi cấu hình" type="number" min={2} max={20} required value={frames} onChange={event => setFrames(event.target.value)} className="rounded-lg border border-[var(--line)] p-2 text-sm" /></label></div>
          <Button type="submit" loading={busy} disabled={!message.trim() || !controlsValid || running || !registry?.agent_enabled || !registry?.carla_client_installed}>Gửi & chạy thí nghiệm</Button>
          <p className="text-xs leading-5 text-[var(--muted)]">Mỗi yêu cầu tạo một study mới. Tối đa 3 cảnh và 3 cấu hình ngoài baseline. Chỉ chạy một worker CARLA; nếu study chờ lâu, kiểm tra worker đang mở.</p>
        </form>
        <div className="grid gap-2"><p className="text-xs font-medium text-[var(--muted)]">Gợi ý prompt</p>{examples.map(example => <button key={example} onClick={() => setMessage(example)} className="rounded-lg border border-[var(--line)] p-3 text-left text-xs leading-5 hover:bg-[var(--surface-subtle)]">{example}</button>)}</div>
        {history.length > 0 && <div className="grid gap-2 border-t border-[var(--line)] pt-4"><h3 className="text-sm font-semibold">Lịch sử thí nghiệm</h3>{history.map(item => <button key={item.id} onClick={() => choose(item)} aria-pressed={item.id === study?.id} className="rounded-lg border border-[var(--line)] p-3 text-left text-xs aria-pressed:bg-[var(--accent-soft)]"><span className="block truncate">{item.metadata.request ?? item.id}</span><span className="mt-1 block text-[var(--muted)]">{status(item.status)} · {item.total_trials} lần thử</span></button>)}</div>}
      </section>
      <div className="grid gap-5">
        <section className={panel}><div className="flex items-center justify-between gap-4"><h2 className="font-semibold">Tiến độ CARLA</h2>{study?.status === "running" && <Button variant="secondary" loading={busy} onClick={() => void cancel()}>Dừng study</Button>}</div>{study ? <><div className="mt-4 flex justify-between text-sm"><span>{active ? `${active.profile} · ${status(active.status)} · ${active.stage}` : status(study.status)}</span><span>{done}/{study.total_trials}</span></div><progress aria-label="Tiến độ cấu hình thử" value={done} max={study.total_trials} className="my-3 h-2 w-full accent-[var(--accent)]" /><div className="flex flex-wrap gap-2">{study.jobs.map(job => <span key={job.id} title={job.error ?? job.stage} className={`rounded-full px-3 py-2 text-xs ${job.status === "failed" ? "bg-red-50 text-red-800" : "bg-[var(--surface-subtle)]"}`}>{job.profile} · {status(job.status)}</span>)}</div>{study.jobs.filter(job => job.error).map(job => <p role="alert" key={job.id} className="mt-2 text-sm text-red-800">{job.profile}: {job.error}</p>)}</> : <p className="mt-4 text-sm text-[var(--muted)]">Gửi prompt để tạo môi trường, thu dữ liệu và chạy checkpoint.</p>}</section>
        <section className={panel}><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">So sánh chất lượng & lượng dữ liệu</h2>{comparison && <Button variant="secondary" onClick={() => { const blob = new Blob([JSON.stringify({ study, comparison }, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `sensor-study-${study?.id}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}>Tải báo cáo JSON</Button>}</div>
          {comparison && study ? comparison.environments.map(environment => <div key={environment.environment} className="mt-5"><p className="mb-3 text-sm font-medium">{environment.scenario.map} · {environment.scenario.weather}</p><div className="overflow-x-auto"><table className="w-full whitespace-nowrap text-left text-xs"><thead><tr className="border-b border-[var(--line)] text-[var(--muted)]">{["Cấu hình", "Điểm/s", "IoU", "Giảm IoU", "MB/s", "Giảm dữ liệu", "p95 ms", "Kết quả"].map(label => <th key={label} className="px-2 py-3 font-medium">{label}</th>)}</tr></thead><tbody>{environment.trials.map(row => {
            const lidar = row.profile === "baseline" ? environment.scenario.lidar : study.spec.profiles.find(profile => profile.name === row.profile)?.lidar;
            const eligible = row.status === "succeeded" && row.reference_matches_baseline && row.iou_drop !== null && row.iou_drop <= study.spec.max_iou_drop;
            const verdict = row.status !== "succeeded" ? "Lỗi" : !row.reference_matches_baseline ? "Không so sánh được" : eligible ? "Đạt" : "Không đạt";
            return <tr key={row.job_id} className={`border-b border-[var(--line)] ${row.profile === environment.provisional_selected ? "bg-[var(--accent-soft)]" : ""}`}><td className="px-2 py-3"><strong>{row.profile}</strong><span className="mt-1 block text-[var(--muted)]">{lidar?.channels} kênh · {lidar?.range_m} m</span></td><td className="px-2 py-3">{lidar?.points_per_second.toLocaleString()}</td><td className="px-2 py-3">{number(row.occupied_iou)}</td><td className="px-2 py-3">{number(row.iou_drop)}</td><td className="px-2 py-3">{number(row.lidar_bytes_per_second == null ? null : row.lidar_bytes_per_second / 1e6, 2)}</td><td className="px-2 py-3">{row.data_reduction_fraction == null ? "—" : `${(row.data_reduction_fraction * 100).toFixed(1)}%`}</td><td className="px-2 py-3">{number(row.latency_model_only_ms?.p95, 1)}</td><td className={`px-2 py-3 font-semibold ${eligible ? "text-[var(--accent)]" : "text-red-800"}`}>{verdict}</td></tr>;
          })}</tbody></table></div><p className="mt-3 rounded-lg bg-[var(--surface-subtle)] p-3 text-sm">{environment.provisional_selected ? <>Đề xuất tạm thời: <strong>{environment.provisional_selected}</strong> — ít dữ liệu nhất trong các cấu hình đạt ngưỡng đã thử.</> : "Chưa có cấu hình đủ điều kiện để đề xuất."}</p></div>) : <p className="mt-4 text-sm text-[var(--muted)]">Metric xuất hiện sau khi baseline và các cấu hình thử hoàn tất.</p>}
          {study?.status === "completed" && !study.summary && <Button className="mt-4" variant="secondary" loading={explaining} onClick={() => void explain()}>Agent giải thích kết quả</Button>}
        </section>
        <section className={panel}><h2 className="font-semibold">Dữ liệu CARLA & output checkpoint</h2>{preview ? <><div className="my-4 flex flex-wrap items-center gap-3"><label className="text-xs">Lần thử <select aria-label="Lần thử xem dữ liệu" value={preview.id} onChange={event => { setSelectedJob(event.target.value); setFrame(0); }} className="ml-2 rounded-lg border border-[var(--line)] p-2">{completedJobs.map(job => <option key={job.id} value={job.id}>{job.profile} · cảnh {job.environment + 1}</option>)}</select></label><label className="text-xs">Frame <input aria-label="Chọn frame" type="range" min={0} max={(preview.result?.manifest.frames.length ?? 1) - 1} value={previewFrame} onChange={event => setFrame(Number(event.target.value))} className="mx-2 align-middle accent-[var(--accent)]" />{previewFrame + 1}/{preview.result?.manifest.frames.length}</label></div><div className="grid gap-4 md:grid-cols-2"><div><Image unoptimized width={640} height={360} src={`${base}/${preview.id}/camera?index=${previewFrame}`} alt={`Camera CARLA, ${preview.profile}, frame ${previewFrame + 1}`} className="h-auto w-full rounded-lg" /><p className="mt-2 text-xs text-[var(--muted)]">RGB để kiểm tra cảnh; checkpoint này dùng LiDAR.</p></div><OutputPreview job={preview.id} frame={previewFrame} /></div><div className="mt-4 flex flex-wrap gap-4 text-sm text-[var(--accent)]"><a className="underline" href={`${base}/${preview.id}/capture/${previewFrame}/npz`}>Tải input LiDAR/BEV</a><a className="underline" href={`${base}/${preview.id}/capture/${previewFrame}/json`}>Tải geometry</a><a className="underline" href={`${base}/${preview.id}/predictions/occupancy_lidar/${previewFrame}`} target="_blank" rel="noreferrer">Xem output JSON</a></div></> : <p className="mt-4 text-sm text-[var(--muted)]">Chưa có lần thử thành công để xem dữ liệu.</p>}</section>
        <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-950">IoU được đo trên nhãn occupancy proxy. Chưa chứng minh mức thấp nhất toàn cục hoặc an toàn ngoài thực tế. Mưa/sương mù hiện thay đổi RGB; chưa xác minh suy giảm LiDAR do thời tiết. Ngưỡng giảm IoU so với baseline không thay thế yêu cầu IoU tuyệt đối tối thiểu.</aside>
      </div>
    </div>
  </div>;
}
