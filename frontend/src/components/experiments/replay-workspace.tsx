"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { apiJson } from "@/lib/lab-api";
import { SensorComparison } from "./sensor-comparison";
import { useExperimentSession } from "./use-experiment-session";

const base = "/api/v1/experiments";
type Scene = { id: string; description: string; frames: number; mean_annotated_objects: number };
type Catalog = { ready: boolean; error: string | null; scenes: Scene[]; cameras: string[]; radars: string[];
  models: string[]; camera_detector_configured: boolean };
type Camera = { mode: string; mean_psnr_db: number; detection_retention: number | null };
type ModelResult = { metrics: { occupied_iou: number | null; object_recall: number | null } };
type Trial = { job_id: string; profile: string; status: string; error: string | null;
  reference_matches_baseline: boolean; sensor_cost: Record<string, number>; camera: Camera;
  models: Record<string, ModelResult> };
type Choice = { profile: string; model?: string; payload_bytes_per_frame?: number; encoded_bytes_per_frame?: number };
type Environment = { environment: number; scenario: { scene_id: string; weather: string; frames: number };
  trials: Trial[]; model_choices: Record<string, Choice | null>; provisional_selected: Choice | null;
  camera_choice: Choice | null; camera_evaluation_mode: string };
type Report = { study_id: string; environments: Environment[]; limitations: string[] };
type Study = { id: string; status: string; total_trials: number; checkpoint_sha256: string;
  spec: { cameras: string[]; model_ids: string[]; max_iou_drop: number;
    scenarios: { scene_id: string; frames: number; weather: string; seed: number }[];
    profiles: { name: string; lidar: { keep_fraction: number }; radar: { keep_fraction: number };
      camera: { scale: number; jpeg_quality: number } }[] };
  metadata: { orchestration_error?: string; request?: string; same_plan_as?: string | null };
  jobs: { id: string; profile: string; status: string; stage: string; error: string | null }[];
  summary: { explanation: string } | null };
const modelNames: Record<string, string> = { occupancy_lidar: "LiDAR", occupancy_radar: "Radar", occupancy_lidar_radar: "LiDAR + Radar" };
const cameraNames: Record<string, string> = { CAM_FRONT: "Trước", CAM_FRONT_LEFT: "Trước trái", CAM_FRONT_RIGHT: "Trước phải", CAM_BACK: "Sau", CAM_BACK_LEFT: "Sau trái", CAM_BACK_RIGHT: "Sau phải" };
const statusNames: Record<string, string> = { queued: "Đang chờ", running: "Đang chạy", succeeded: "Hoàn thành", completed: "Hoàn thành", failed: "Có lỗi", cancelled: "Đã hủy" };
const profileNames: Record<string, string> = { baseline: "Cấu hình gốc", half: "Giữ 50%", quarter: "Giữ 25%" };
const profileName = (name: string) => profileNames[name] ?? name;
const scopedUrl = (path: string, session: string) => `${base}${path}${path.includes("?") ? "&" : "?"}session=${session}`;

async function sessionPost<T>(path: string, session: string, body: unknown = {}): Promise<T> {
  const response = await fetch(scopedUrl(path, session), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data as T;
}
const percent = (v: number | null | undefined) => v == null ? "—" : `${(v * 100).toFixed(1)}%`;
const number = (v: number | undefined) => v == null ? "—" : `${(v / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} kB`;

function selectedStats(env: Environment) {
  const choice = env.provisional_selected;
  const baseline = env.trials.find(t => t.profile === "baseline");
  const selected = env.trials.find(t => t.profile === choice?.profile);
  const payload = (t: Trial) => choice?.model === "occupancy_radar" ? t.sensor_cost.radar_payload_bytes
    : choice?.model === "occupancy_lidar_radar" ? t.sensor_cost.lidar_payload_bytes + t.sensor_cost.radar_payload_bytes
      : t.sensor_cost.lidar_payload_bytes;
  return { iou: choice?.model ? selected?.models[choice.model]?.metrics.occupied_iou : null,
    reduction: baseline && selected && payload(baseline) ? 1 - payload(selected) / payload(baseline) : null };
}

export function ReplayWorkspace() {
  const { session, loading, error, end, start } = useExperimentSession();
  return <section className="grid gap-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">04 / AI Agent · Occupancy</p><h1 className="text-2xl font-semibold sm:text-3xl">Tìm cấu hình sensor cho Occupancy</h1><p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">Giảm dữ liệu LiDAR/radar trong khi giữ chất lượng bản đồ vật cản BEV. Agent thử cấu hình trên dữ liệu ghi sẵn và đề xuất phương án dựa trên IoU.</p></div><div className="grid justify-items-end gap-2"><span className="rounded-full bg-[var(--accent-soft)] px-3 py-1.5 text-xs font-medium">{session ? "● Phiên tạm đang mở" : loading ? "Đang mở phiên…" : "Phiên đã kết thúc"}</span>{session ? <Button variant="ghost" loading={loading} onClick={() => void end()}>Kết thúc phiên</Button> : !loading ? <Button onClick={() => void start()}>Bắt đầu phiên mới</Button> : null}</div></header>
    <p className="rounded-xl bg-[var(--accent-soft)] p-4 text-sm"><strong>Mục 04 dành cho Occupancy:</strong> so sánh ba model LiDAR, Radar và LiDAR + Radar trên cùng frame. Camera được đánh giá riêng về chất lượng ảnh và dung lượng. Luồng này chưa tối ưu Detection, Flow hoặc Risk; Lab và Compare phục vụ các kết quả tính sẵn riêng.</p>
    <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-subtle)] p-4 text-xs text-[var(--muted)]">Lịch sử chỉ thuộc phiên này, giữ khi refresh. Đóng tab: tự dọn sau khoảng 30 giây; nếu trình duyệt không gửi tín hiệu đóng, phiên hết hạn sau 3 phút. Kết thúc phiên hủy lượt đang chạy và dọn dữ liệu tạm. Tải báo cáo nếu muốn giữ kết quả.</p>
    {error ? <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
    {session ? <SessionWorkspace key={session} session={session} /> : <div className="rounded-2xl border border-dashed border-[var(--line)] bg-white p-12 text-center text-sm text-[var(--muted)]">{loading ? "Đang kết nối dữ liệu…" : "Phiên đã đóng. Bắt đầu phiên mới để chạy thí nghiệm với lịch sử trống."}</div>}
  </section>;
}

function SessionWorkspace({ session }: { session: string }) {
  const post = <T,>(path: string, body: unknown = {}) => sessionPost<T>(path, session, body);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [message, setMessage] = useState("Thử cả LiDAR, radar và camera ở scene-0103, 2 frames; profile half giữ 50% điểm LiDAR/radar, ảnh nửa độ phân giải, JPEG 80; IoU giảm tối đa 0.02");
  const [studies, setStudies] = useState<Study[]>([]);
  const [selected, setSelected] = useState("");
  const [pendingRequest, setPendingRequest] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [previewId, setPreviewId] = useState("");
  const [previewModel, setPreviewModel] = useState("occupancy_lidar");
  const [previewCamera, setPreviewCamera] = useState("CAM_FRONT");
  const [frame, setFrame] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const chosen = pendingRequest !== null ? undefined : selected ? studies.find(s => s.id === selected) : studies[0];
  const currentReport = report?.study_id === chosen?.id ? report : null;
  const trial = currentReport?.environments.flatMap(e => e.trials).find(t => t.job_id === previewId)
    ?? currentReport?.environments.flatMap(e => e.trials.filter(t => t.status === "succeeded" && t.profile === (e.camera_choice?.profile ?? e.provisional_selected?.profile))).at(0)
    ?? currentReport?.environments.flatMap(e => e.trials).find(t => t.status === "succeeded");
  const environment = currentReport?.environments.find(e => e.trials.some(t => t.job_id === trial?.job_id));
  const studyCameras = chosen?.spec.cameras ?? ["CAM_FRONT"];
  const cameraChannel = studyCameras.includes(previewCamera) ? previewCamera : studyCameras[0];
  const previewFrame = Math.min(frame, Math.max(0, (environment?.scenario.frames ?? 1) - 1));

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([apiJson<Catalog>(`${base}/replay/catalog`, controller.signal),
      apiJson<{ agent_enabled: boolean }>(`${base}/registry`, controller.signal)])
      .then(([data, registry]) => { if (!controller.signal.aborted) { setCatalog(data); setAgentEnabled(registry.agent_enabled); } })
      .catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await apiJson<{ items: Study[] }>(scopedUrl("/replay/studies", session), controller.signal);
        if (!controller.signal.aborted) {
          // A poll started before creation can return an older list. Keep the new study.
          setStudies(previous => [...data.items, ...previous.filter(s => !data.items.some(item => item.id === s.id))]);
          setConnectionError("");
        }
      } catch { if (!controller.signal.aborted) setConnectionError("Kết nối đang gián đoạn. Kết quả sẽ tự cập nhật khi kết nối lại."); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [session]);
  useEffect(() => {
    if (chosen?.status !== "completed") return;
    const controller = new AbortController();
    void apiJson<Report>(scopedUrl(`/sensor-agent/${chosen.id}/comparison`, session), controller.signal)
      .then(data => { if (!controller.signal.aborted) setReport(data); })
      .catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, [chosen?.id, chosen?.status, session]);

  const action = async (operation: () => Promise<Study>, newRequest?: string) => {
    setBusy(true); setError("");
    if (newRequest !== undefined) {
      setPendingRequest(newRequest); setReport(null); setPreviewId(""); setFrame(0);
    }
    try { const study = await operation(); setSelected(study.id); setFrame(0); setPreviewId(""); setReport(null);
      setPendingRequest(null);
      setStudies(previous => [study, ...previous.filter(s => s.id !== study.id)]); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const summarize = async () => {
    if (!chosen) return;
    setBusy(true); setError("");
    try { const summary = await post<{ explanation: string }>(`/sensor-agent/${chosen.id}/summarize`);
      setStudies(previous => previous.map(s => s.id === chosen.id ? { ...s, summary } : s)); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };

  return <div className="grid items-start gap-6 xl:grid-cols-[minmax(300px,0.85fr)_minmax(0,1.35fr)]">
    <section className="grid gap-5 rounded-2xl border border-[var(--line)] bg-white p-5 sm:p-6">
    <div><h2 className="text-lg font-semibold">1. Giao nhiệm vụ cho agent</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">Nêu sensor, môi trường và mức chất lượng cần giữ. Agent sẽ lập kế hoạch thí nghiệm.</p></div>
    {catalog && !catalog.ready ? <p role="alert" className="text-sm text-red-700">{catalog.error ?? "Chưa có dataset."} Chuẩn bị raw nuScenes-mini và cấu hình NUSC_ROOT. Checkpoint có sẵn chưa thay thế dữ liệu sensor gốc.</p> : null}
    {error ? <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error.replace(/^Error: /, "")}</p> : null}
    {connectionError ? <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">{connectionError}</p> : null}
    <label className="grid gap-2 text-sm font-medium">Bạn muốn thử điều gì?<textarea maxLength={2000} rows={7} className="rounded-xl border border-[var(--line)] p-3 text-sm leading-relaxed" value={message} onChange={e => setMessage(e.target.value)} placeholder="Thử LiDAR/radar 50% điểm và camera nửa độ phân giải ở scene-0103, 2 frames" /></label>
    <div className="flex flex-wrap gap-2">{[["Thử nhanh 3 sensor", "Thử cả LiDAR, radar và camera ở scene-0103, 2 frames; profile half giữ 50% điểm LiDAR/radar, ảnh nửa độ phân giải, JPEG 80; IoU giảm tối đa 0.02"], ["Ảnh có hiệu ứng mưa", "So sánh baseline và half cho LiDAR, radar và camera ở scene-0103, 2 frames, hiệu ứng mưa; IoU giảm tối đa 0.02"]].map(([label, prompt]) => <button key={label} onClick={() => setMessage(prompt)} className="rounded-full border border-[var(--line)] px-3 py-2 text-xs hover:bg-[var(--surface-subtle)]">{label}</button>)}</div>
    <p className="text-xs text-[var(--muted)]">Agent lập kế hoạch từ yêu cầu ở trên. Worker đo kết quả trên dữ liệu ghi sẵn.</p>
    {catalog?.ready ? <p className="text-xs text-[var(--muted)]">Scene hiện có: {catalog.scenes.map(s => s.id).join(", ")}. Agent chỉ chạy trên scene có dữ liệu.</p> : null}
    <Button loading={busy} disabled={!catalog?.ready || !agentEnabled || !message.trim()} onClick={() => void action(() => post<Study>("/replay/agent/start", { message }), message)}>Để agent lập kế hoạch và chạy</Button>
    <p className="text-center text-xs text-[var(--muted)]">Có dùng token API cho bước lập kế hoạch. Giải thích kết quả được gọi riêng khi bạn yêu cầu.</p>
    {!agentEnabled ? <p className="text-xs text-[var(--muted)]">Agent chưa được bật hoặc chưa có API key. Bật agent và cấu hình API key ở backend để bắt đầu.</p> : null}
    <details className="text-xs text-[var(--muted)]"><summary className="cursor-pointer">Các phép đo này có ý nghĩa gì?</summary><p className="mt-2 leading-relaxed">Camera {catalog?.camera_detector_configured ? "đo độ giữ lại detection bằng detector" : "đo chất lượng ảnh/dung lượng, chưa có detector"}. Mưa/sương mù là hiệu ứng ảnh, chưa mô phỏng vật lý sensor. Kết quả là lựa chọn thử nghiệm. Giảm dữ liệu chưa chứng minh giảm điện năng hoặc chi phí phần cứng.</p></details>
    </section>
    <section className="grid min-w-0 gap-5 rounded-2xl border border-[var(--line)] bg-white p-5 sm:p-6">
    <div className="flex items-center justify-between gap-2"><h2 className="text-lg font-semibold">2. Kết quả trong phiên</h2><span className="text-xs text-[var(--muted)]">{studies.length} thí nghiệm</span></div>
    {studies.length ? <Select label="Lịch sử thí nghiệm trong phiên" disabled={busy} value={chosen?.id ?? ""} onChange={e => { if (!e.target.value) return; setPendingRequest(null); setError(""); setSelected(e.target.value); setReport(null); setPreviewId(""); setFrame(0); }}>
      <option value="" disabled>Chọn một lượt cũ để xem lại</option>
      {studies.map((s, i) => <option key={s.id} value={s.id}>Lượt {studies.length - i} · {s.spec.scenarios.map(scene => scene.scene_id).join(", ")} · {statusNames[s.status] ?? s.status}</option>)}
    </Select> : null}
    {!chosen ? <div role={pendingRequest !== null ? "status" : undefined} className="grid min-h-72 content-center gap-3 rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-subtle)] p-6 text-center">
      <h3 className="font-semibold">{pendingRequest !== null ? busy ? "Agent đang lập kế hoạch cho yêu cầu mới…" : "Yêu cầu mới chưa tạo được thí nghiệm" : "Sẵn sàng thử cấu hình đầu tiên"}</h3>
      {pendingRequest !== null ? <><p className="whitespace-pre-wrap text-sm">{pendingRequest}</p>{error ? <p className="text-sm text-red-700">{error.replace(/^Error: /, "")}</p> : null}<p className="text-xs text-[var(--muted)]">Kết quả lượt trước chỉ hiển thị khi bạn chọn lại trong lịch sử.</p></> : <p className="mx-auto max-w-sm text-sm text-[var(--muted)]">Nhập yêu cầu rồi bấm “Để agent lập kế hoạch và chạy” để xem kết quả.</p>}
    </div> : null}
    {chosen ? <><div className="flex items-center justify-between gap-3"><span className="rounded-full bg-[var(--accent-soft)] px-3 py-1.5 text-xs font-semibold">{statusNames[chosen.status] ?? chosen.status}</span><p className="text-xs text-[var(--muted)]">{chosen.jobs.filter(j => ["succeeded", "failed", "cancelled"].includes(j.status)).length}/{chosen.total_trials} cấu hình đã xử lý</p></div>
      <div className="grid gap-3 rounded-xl bg-[var(--surface-subtle)] p-4"><h3 className="text-sm font-semibold">Kế hoạch thực tế của lượt {chosen.id.slice(0, 8)}</h3>
        {chosen.metadata.request ? <p className="whitespace-pre-wrap text-xs"><strong>Yêu cầu đã gửi:</strong> {chosen.metadata.request}</p> : null}
        <p className="text-xs">Model: {chosen.spec.model_ids.map(m => modelNames[m] ?? m).join(", ")} · IoU được giảm tối đa: {chosen.spec.max_iou_drop}.</p>
        {chosen.spec.scenarios.map((s, i) => <p key={i} className="text-xs">{s.scene_id} · {s.frames} frames · {s.weather === "original" ? "Ảnh gốc" : s.weather === "rain" ? "Hiệu ứng mưa" : "Hiệu ứng sương mù"} · seed {s.seed}</p>)}
        {chosen.spec.profiles.map(p => <p key={p.name} className="text-xs">{profileName(p.name)}: LiDAR giữ {percent(p.lidar.keep_fraction)} · radar giữ {percent(p.radar.keep_fraction)} · ảnh {percent(p.camera.scale)} kích thước mỗi chiều · JPEG {p.camera.jpeg_quality}</p>)}
        {chosen.metadata.same_plan_as ? <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Agent tạo cùng cấu hình với lượt {chosen.metadata.same_plan_as.slice(0, 8)}. Cùng dữ liệu, checkpoint và seed thường cho cùng kết quả inference.</p> : null}
        <details><summary className="cursor-pointer text-xs">Xem đầy đủ cấu hình và checkpoint</summary><pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-white p-3 text-xs">{JSON.stringify({ study_id: chosen.id, checkpoint_sha256: chosen.checkpoint_sha256, spec: chosen.spec }, null, 2)}</pre></details>
      </div>
      <progress aria-label="Tiến độ thí nghiệm" max={chosen.total_trials} value={chosen.jobs.filter(j => ["succeeded", "failed", "cancelled"].includes(j.status)).length} className="h-2 w-full accent-[var(--accent)]" />
      {chosen.status === "running" ? <Button variant="secondary" loading={busy} onClick={() => void action(() => post<Study>(`/sensor-agent/${chosen.id}/cancel`))}>Hủy study</Button> : null}
      {chosen.metadata.orchestration_error ? <p role="alert">{chosen.metadata.orchestration_error}</p> : null}
      <ul className="flex flex-wrap gap-2 text-xs">{chosen.jobs.map(j => <li key={j.id} className={`rounded-lg p-3 ${j.status === "failed" ? "bg-red-50 text-red-700" : "bg-[var(--surface-subtle)]"}`}>{profileName(j.profile)} · {statusNames[j.status] ?? j.status} {j.error}</li>)}</ul></> : null}
    {currentReport ? <>
      {currentReport.environments.map(env => <div key={env.environment} className="grid gap-3 border-t pt-4">
        <h2 className="font-semibold">{env.scenario.scene_id} · {env.scenario.weather}</h2>
        <div className="grid gap-3 sm:grid-cols-2"><div className="rounded-xl bg-[var(--accent-soft)] p-4"><p className="text-xs text-[var(--muted)]">Cấu hình điểm đề xuất</p><p className="mt-2 font-semibold">{env.provisional_selected ? `${modelNames[env.provisional_selected.model ?? ""] ?? env.provisional_selected.model} · ${profileName(env.provisional_selected.profile)}` : "Chưa đủ bằng chứng chọn"}</p></div><div className="rounded-xl bg-[var(--surface-subtle)] p-4"><p className="text-xs text-[var(--muted)]">Cấu hình camera đề xuất</p><p className="mt-2 font-semibold">{env.camera_choice ? profileName(env.camera_choice.profile) : "Chưa đủ bằng chứng"}</p><p className="mt-1 text-xs text-[var(--muted)]">{env.camera_evaluation_mode === "image_fidelity_only" ? "Dựa trên chất lượng ảnh" : "Dựa trên giữ lại detection"}</p></div></div>
        <div className="grid grid-cols-2 gap-3"><div className="rounded-xl border border-[var(--line)] p-4"><p className="text-xs text-[var(--muted)]">IoU cấu hình đề xuất</p><p className="mt-1 text-2xl font-semibold">{percent(selectedStats(env).iou)}</p></div><div className="rounded-xl border border-[var(--line)] p-4"><p className="text-xs text-[var(--muted)]">Dữ liệu điểm giảm</p><p className="mt-1 text-2xl font-semibold">{percent(selectedStats(env).reduction)}</p><p className="mt-1 text-xs text-[var(--muted)]">So với cấu hình gốc của model này</p></div></div>
        <details><summary className="cursor-pointer text-sm font-medium">Xem bảng số đo chi tiết</summary><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[700px] text-left text-xs"><caption className="mb-2 text-left text-[var(--muted)]">Dung lượng trung bình mỗi frame. IoU và PSNR cao hơn là tốt hơn khi so trên cùng tham chiếu.</caption><thead><tr>{["Cấu hình", "Tham chiếu", "LiDAR IoU", "Radar IoU", "Fusion IoU", "LiDAR", "Radar", "Camera", "PSNR dB", "Detection"].map(h => <th key={h} className="p-2">{h}</th>)}</tr></thead><tbody>{env.trials.map(t => <tr key={t.job_id} className="border-t"><td className="p-2 font-medium">{profileName(t.profile)}</td><td>{t.reference_matches_baseline ? "Khớp" : "Không khớp/lỗi"}</td>{["occupancy_lidar", "occupancy_radar", "occupancy_lidar_radar"].map(m => <td key={m} className="p-2">{percent(t.models[m]?.metrics.occupied_iou)}</td>)}<td>{number(t.sensor_cost.lidar_payload_bytes)}</td><td>{number(t.sensor_cost.radar_payload_bytes)}</td><td>{number(t.sensor_cost.camera_encoded_bytes)}</td><td>{t.camera.mean_psnr_db?.toFixed(1) ?? "—"}</td><td>{percent(t.camera.detection_retention)}</td></tr>)}</tbody></table></div></details>
      </div>)}
      <h3 className="mt-2 text-lg font-semibold">3. Xem ảnh và giải thích</h3>
      <div className="grid gap-3 sm:grid-cols-3"><Select label="Cấu hình xem trước" value={trial?.job_id ?? ""} onChange={e => setPreviewId(e.target.value)}>{currentReport.environments.flatMap(e => e.trials).filter(t => t.status === "succeeded").map(t => <option key={t.job_id} value={t.job_id}>{profileName(t.profile)}</option>)}</Select>
        <Select label="Model BEV" value={previewModel} onChange={e => setPreviewModel(e.target.value)}>{Object.keys(trial?.models ?? {}).map(m => <option key={m} value={m}>{modelNames[m] ?? m}</option>)}</Select>
        <label className="grid gap-2 text-xs">Frame<input type="number" min={0} max={(environment?.scenario.frames ?? 1) - 1} value={previewFrame} onChange={e => setFrame(Number(e.target.value))} className="rounded border p-2" /></label></div>
      {trial ? <><Select label="Góc nhìn camera" value={cameraChannel} onChange={e => setPreviewCamera(e.target.value)}>{studyCameras.map(c => <option key={c} value={c}>{cameraNames[c] ?? c}</option>)}</Select>{environment?.trials.find(t => t.profile === "baseline" && t.status === "succeeded") && trial.reference_matches_baseline ? <SensorComparison baseline={environment.trials.find(t => t.profile === "baseline")!.job_id} candidate={trial.job_id} model={Object.keys(trial.models).includes(previewModel) ? previewModel : Object.keys(trial.models)[0]} frame={previewFrame} session={session} channel={cameraChannel} /> : <p className="text-xs text-amber-800">Chưa có baseline cùng tham chiếu để đối chiếu trực quan.</p>}
        <div className="grid gap-3 sm:grid-cols-2">{[true, false].map(reference => <figure key={String(reference)} className="overflow-hidden rounded-xl border border-[var(--line)]"><figcaption className="bg-[var(--surface-subtle)] px-3 py-2 text-xs font-medium">{reference ? "Ảnh tham chiếu" : `Ảnh sau giảm dữ liệu · ${profileName(trial.profile)}`}</figcaption><Image unoptimized width={800} height={450} alt={reference ? "Ảnh camera tham chiếu" : "Ảnh camera sau giảm dữ liệu"} src={scopedUrl(`/${trial.job_id}/camera?index=${previewFrame}&channel=${cameraChannel}&reference=${reference}`, session)} className="h-auto w-full" /></figure>)}</div></> : null}
    {!chosen?.summary ? <Button variant="secondary" loading={busy} disabled={!agentEnabled} onClick={() => void summarize()}>Nhờ agent giải thích kết quả · dùng token API</Button> : null}
      {chosen?.summary ? <div className="rounded-xl bg-[var(--accent-soft)] p-4"><h3 className="mb-2 text-sm font-semibold">Nhận xét của agent</h3><p className="whitespace-pre-wrap text-sm leading-relaxed">{chosen.summary.explanation}</p></div> : null}
      <Button variant="secondary" onClick={() => { const blob = new Blob([JSON.stringify(currentReport, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `sensor-study-${currentReport.study_id}.json`; a.click(); URL.revokeObjectURL(url); }}>Tải báo cáo JSON</Button>
      <p className="text-xs text-[var(--muted)]">Đánh giá trên các frame đã chọn. Camera chưa đánh giá độ chính xác ground truth. Cần nhiều cảnh và nhãn để kết luận về khả năng hoạt động thực tế.</p>
    </> : null}
  </section></div>;
}
