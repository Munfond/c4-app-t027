"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/lab-api";
import { Button } from "@/components/ui/button";
import { CapturePlayback } from "./capture-playback";

const base = "/api/v1/experiments/native-online";
type Profile = { channels: number; points_per_second: number };
type Trace = { index: number; current_action: number; next_action: number; current_profile: Profile;
  applies_to_capture_index: number | null; cpu_feature_model_ms: number; cpu_policy_ms: number | null };
type Run = { id: string; ready: true; mode: string; frames: number; decisions: number; interval: number; timestamps: number[];
  trace: Trace[]; route: number; seed: number; reference_sha256: string; report_sha256: string;
  artifact_audit_sha256: string; policy_sha256: string | null; checkpoint_sha256: string; legacy_timing: boolean;
  metrics: { occupied_iou: number | null; class_iou: { object: number | null } }; limits: string[] };
const labels: Record<string, string> = { ppo: "PPO · capture trực tiếp", full_baseline: "Cấu hình cố định · đối chứng",
  diagnostic_schedule_not_policy: "Kiểm tra chuyển sensor · lịch cố định" };
const profile = (p: Profile) => `${p.channels} kênh · ${p.points_per_second / 1000}k điểm/s`;
const pct = (v: number | null) => v == null ? "Chưa đo" : `${(v * 100).toFixed(1)}%`;

function PairedEvidence({ runs, onPreview }: { runs: Run[]; onPreview: (run: string) => void }) {
  const fixed = runs.find(run => run.id === "full20-retry1" && run.mode === "full_baseline");
  const policy = runs.find(run => run.id === "ppo20" && run.mode === "ppo");
  if (!fixed || !policy) return null;
  const comparable = fixed.reference_sha256 === policy.reference_sha256 && fixed.frames === policy.frames
    && fixed.route === policy.route && fixed.seed === policy.seed && fixed.checkpoint_sha256 === policy.checkpoint_sha256;
  if (!comparable) return <p role="status" className="agent-small">Hai lượt 20 frame chưa khớp cảnh và nguồn tham chiếu; chưa thể kết luận PPO tốt hơn.</p>;
  const unchanged = policy.trace.every((row, i) => row.current_action === fixed.trace[i].current_action
    && row.next_action === fixed.trace[i].next_action);
  const equal = policy.metrics.occupied_iou != null && policy.metrics.class_iou.object != null
    && policy.metrics.occupied_iou === fixed.metrics.occupied_iou
    && policy.metrics.class_iou.object === fixed.metrics.class_iou.object;
  return <section aria-label="Đối chiếu PPO và cấu hình cố định" className="border-l-2 border-[var(--accent)] pl-3">
    <strong className="text-sm">{equal && unchanged ? "PPO giữ mặc định · chưa có cải thiện" : "Đối chiếu cùng cảnh · 20 frame"}</strong>
    <p className="agent-small">Cùng route {policy.route}, seed {policy.seed}, model và SHA tham chiếu. {equal && unchanged
      ? `Cả ${policy.decisions} quyết định đều giữ ${profile(policy.trace[0].current_profile)}; chất lượng bằng cấu hình cố định.`
      : "Xem hai lượt và trace trước khi lựa chọn cấu hình."}</p>
    <table className="w-full text-left text-xs tabular-nums">
      <caption className="sr-only">IoU trên ô semantic LiDAR đã quan sát; chưa phải độ tin cậy ngoài thực tế.</caption>
      <thead><tr><th scope="col" className="py-2">Lượt chạy</th><th scope="col">Occupied IoU</th><th scope="col">Object IoU</th></tr></thead>
      <tbody>{[fixed, policy].map(run => <tr key={run.id}>
        <th scope="row" className="py-2 font-normal">{run.mode === "ppo" ? "PPO" : "Cố định"}</th>
        <td>{pct(run.metrics.occupied_iou)}</td><td>{pct(run.metrics.class_iou.object)}</td>
      </tr>)}</tbody>
    </table>
    <div className="flex flex-wrap gap-2 py-2"><Button variant="secondary" onClick={() => onPreview(fixed.id)}>Xem đối chứng</Button>
      <Button variant="secondary" onClick={() => onPreview(policy.id)}>Xem PPO · 20 frame</Button></div>
    <details className="agent-small"><summary className="cursor-pointer py-2">Bằng chứng của phép đối chiếu</summary>
      <p className="break-all">Reference SHA: <code>{policy.reference_sha256}</code></p>
      <a href={`${base}/${fixed.id}/report`} download className="agent-text-button">Tải trace đối chứng</a>{" · "}
      <a href={`${base}/${policy.id}/report`} download className="agent-text-button">Tải trace PPO</a>
      <p>Đây là inference của policy đã học. Không cập nhật policy bằng test này; chưa chứng minh tiết kiệm điện hoặc thích nghi thời tiết.</p>
    </details>
  </section>;
}

export function NativeOnlineEvidence({ onPreview }: { onPreview: (run: string) => void }) {
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [unavailable, setUnavailable] = useState<string[]>([]);
  const [pending, setPending] = useState<{id: string; status: string; frames: number}[]>([]);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void apiJson<{items: Run[]; unavailable: string[]; pending: {id: string; status: string; frames: number}[]}>(base, controller.signal).then(data => {
      if (!controller.signal.aborted) { setRuns(data.items); setUnavailable(data.unavailable); setPending(data.pending); setError(""); }
    }).catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, [open, attempt]);
  return <details className="agent-review" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary className="cursor-pointer py-3 font-semibold">PPO trong CARLA · xem quyết định từng frame</summary>
    {open && <div className="grid gap-3">
      <p className="agent-small">Policy đã học được dùng trong lúc capture. Đây là bản ghi lượt chạy trực tiếp; Play chỉ phát lại, không train hay khởi động mô phỏng.</p>
      <p className="agent-small">RL (Reinforcement Learning) là học tăng cường; PPO (Proximal Policy Optimization) là thuật toán dùng để học cách chọn cấu hình.</p>
      {error && <p role="alert" className="agent-error">{error}</p>}
      {!runs && !error && <p role="status" className="agent-small">Đang kiểm tra bản ghi…</p>}
      {runs?.length === 0 && <p className="agent-small">Server này chưa có capture online đã kiểm định.</p>}
      {runs && <PairedEvidence runs={runs} onPreview={onPreview} />}
      {runs?.map(run => <div key={run.id} className="border-t border-[var(--line)] pt-3">
        <strong className="text-xs">{labels[run.mode] ?? run.mode}</strong>
        <p className="agent-small">{run.frames} frame · {run.decisions} quyết định · {run.mode === "diagnostic_schedule_not_policy" ? "Không phải quyết định PPO" : `Đổi cấu hình ${run.trace.slice(0,-1).filter(row => row.current_action !== row.next_action).length} lần`}</p>
        <Button variant="secondary" onClick={() => onPreview(run.id)}>Xem capture & quyết định →</Button>
      </div>)}
      {pending.map(item => <p key={item.id} className="agent-small">{item.id}: {item.status === "planned" ? "Đã đăng ký kế hoạch · chưa chạy" : item.status === "running" ? "Đang capture" : "Lượt thử chưa hoàn tất"} · {item.frames} frame được xử lý</p>)}
      {!!unavailable.length && <p role="alert" className="agent-small">{unavailable.length} bản ghi thiếu hoặc sai checksum; đã chặn preview.</p>}
      <p className="agent-small">Cả 12 LiDAR vẫn hoạt động; policy chỉ chọn luồng đưa vào model. Chưa chứng minh giảm công suất cảm biến hoặc tốt hơn cấu hình cố định.</p>
      <button className="agent-text-button" type="button" onClick={() => setAttempt(v => v + 1)}>Kiểm tra bản ghi mới</button>
    </div>}
  </details>;
}

export function NativeOnlinePreview({ run, active }: { run: string; active: boolean }) {
  const [data, setData] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void apiJson<Run>(`${base}/${encodeURIComponent(run)}/report`, controller.signal).then(value => {
      if (!controller.signal.aborted) { setData(value); setError(""); }
    }).catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, [run, attempt]);
  if (!data) return <div role={error ? "alert" : "status"} className="py-8">{error || "Đang kiểm tra capture đồng bộ…"}{error && <Button variant="secondary" onClick={() => setAttempt(v => v + 1)}>Thử lại</Button>}</div>;
  const notes = data.trace.map(row => `LiDAR đang dùng: ${profile(row.current_profile)}. ${row.applies_to_capture_index == null ? "Frame cuối, không tạo quyết định tiếp." : `Frame ${row.applies_to_capture_index + 1} sẽ dùng ${profile(data.trace[row.applies_to_capture_index].current_profile)}.`} Feature + model CPU: ${row.cpu_feature_model_ms.toFixed(1)} ms${row.cpu_policy_ms != null ? ` · chọn cấu hình: ${row.cpu_policy_ms.toFixed(1)} ms` : ""}.`);
  return <section className="grid gap-5" aria-label="Capture kiểm chứng chọn LiDAR online">
    <header className="flex flex-wrap items-end justify-between gap-4 pt-4">
      <div><p className="eyebrow">CARLA · NATIVE INPUT · FROZEN POLICY</p><h1 className="text-2xl font-semibold">{labels[data.mode] ?? data.mode}</h1><p className="mt-2 text-sm text-[var(--muted)]">Town01 · clear · route {data.route} · seed {data.seed} · {data.frames} frame</p></div>
      <dl className="flex gap-6 text-sm tabular-nums"><div><dt className="text-[var(--muted)]">Occupied IoU</dt><dd className="text-xl">{pct(data.metrics.occupied_iou)}</dd></div><div><dt className="text-[var(--muted)]">Object IoU</dt><dd className="text-xl">{pct(data.metrics.class_iou.object)}</dd></div></dl>
    </header>
    <p className="border-l-2 border-[var(--accent)] pl-3 text-sm">{data.mode === "ppo" ? "Policy đọc LiDAR hiện tại và độ trễ đã đo; chọn cấu hình cho frame kế tiếp. Nhãn tham chiếu chỉ dùng để chấm điểm sau capture." : data.mode === "full_baseline" ? "Cấu hình được giữ cố định để đối chứng với PPO." : "Lịch chuyển cấu hình cố định kiểm tra đường truyền sensor; kết quả này không phải khả năng thích nghi của PPO."} Lượt thử này chưa đủ kết luận khả năng tổng quát.</p>
    <CapturePlayback job={run} model="occupancy_lidar" count={data.frames} interval={data.interval} camera active={active} timestamps={data.timestamps} apiBase={`${base}/${encodeURIComponent(run)}`} frameNotes={notes} />
    <details><summary className="cursor-pointer py-2 text-sm">Đối chiếu trace & nguồn kiểm chứng</summary>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs tabular-nums"><caption className="py-2 text-left text-[var(--muted)]">Cấu hình đang dùng và quyết định cho frame kế tiếp; model occupancy LiDAR giữ nguyên.</caption><thead><tr><th scope="col" className="py-2">Frame</th><th scope="col">LiDAR đang dùng</th><th scope="col">Action kế tiếp</th><th scope="col">Feature + model</th><th scope="col">Chọn profile</th></tr></thead><tbody>{data.trace.map(row => <tr key={row.index}><th scope="row" className="border-t border-[var(--line)] py-2">{row.index + 1}</th><td className="border-t border-[var(--line)]">{profile(row.current_profile)}</td><td className="border-t border-[var(--line)]">{row.applies_to_capture_index == null ? "Kết thúc" : `${row.next_action + 1}/12`}</td><td className="border-t border-[var(--line)]">{row.cpu_feature_model_ms.toFixed(1)} ms</td><td className="border-t border-[var(--line)]">{row.cpu_policy_ms == null ? "—" : `${row.cpu_policy_ms.toFixed(1)} ms`}</td></tr>)}</tbody></table></div>
      {data.legacy_timing && <p className="text-xs text-[var(--muted)]">Bản diagnostic cũ chỉ lưu feature + model; không có phép đo model-only riêng.</p>}
      {[ ["Report",data.report_sha256], ["Artifact audit",data.artifact_audit_sha256], ["Reference",data.reference_sha256], ["Policy",data.policy_sha256], ["Model",data.checkpoint_sha256] ].map(([label, hash]) => hash && <p key={label} className="my-2 break-all text-xs"><span className="text-[var(--muted)]">{label}: </span><code>{hash}</code></p>)}
      <a href={`${base}/${encodeURIComponent(run)}/report`} download className="agent-tools-button">Tải snapshot trace ↓</a>
      <ul className="list-disc pl-4 text-xs text-[var(--muted)]"><li>Reference chỉ chấm ô semantic LiDAR đã quan sát; ô chưa thấy không được coi là trống.</li><li>12 sensor vẫn chạy; chọn input không phải tắt phần cứng.</li><li>Chưa có weather/radar/ROS2 hoặc điều khiển xe bằng PPO.</li><li>0,5 giây giữa frame trong mô phỏng không bảo đảm chạy thời gian thực.</li></ul>
    </details>
  </section>;
}
