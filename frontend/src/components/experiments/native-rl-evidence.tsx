"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/lab-api";
import { Button } from "@/components/ui/button";

type Metrics = { occupied_iou: number | null; object_iou: number | null; latency_p95_ms: number;
  decisions: number; action_counts: Record<string, number>; switches: number };
type Evidence = { ready: false; notice: string; phase: string; completed?: number; total?: number;
  frame_progress?: { completed: number; total: number } | null; failed_retries?: number } |
  { ready: true; evidence_sha256: string; report: { actual_steps: number; selected_policy_trained_steps: number;
    no_improvement_over_full: boolean; no_improvement_over_best_fixed: boolean; profiles: { channels: number; points_per_second: number }[];
    test_results: Record<string, Metrics>; dataset_sha256: string; checkpoint_sha256: string; limitations: string[] } };
const base = "/api/v1/experiments/native-rl";
const pct = (v: number | null) => v == null ? "—" : `${(100 * v).toFixed(1)}%`;
const phases: Record<string, string> = { capturing: "Đang thu dữ liệu", capture_completed: "Capture đủ · chờ kiểm định và training",
  incomplete_failed: "Capture chưa hoàn tất · cần xử lý lỗi", incomplete_interrupted: "Capture bị ngắt · giữ dữ liệu", unavailable: "Chưa có dữ liệu native" };

export function NativeRlEvidence() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await apiJson<Evidence>(base, controller.signal);
        if (controller.signal.aborted) return;
        setData(value); setError("");
        if (!value.ready) timer = setTimeout(load, 5000);
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause));
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [open, attempt]);
  const report = data?.ready ? data.report : null;
  function label(id: string) {
    if (id === "ppo") return "Policy PPO";
    const profile = report?.profiles[Number(id.replace("fixed_", ""))];
    return profile ? `${profile.channels} kênh · ${profile.points_per_second / 1000}k điểm/s` : id;
  }
  function rows(ids: string[]) {
    return <div className="overflow-x-auto"><table className="w-full text-left text-xs tabular-nums">
      <caption className="pb-2 text-left text-[var(--muted)]">Cùng 19 quyết định trên một route test độc lập · frame 0 bootstrap báo riêng</caption>
      <thead><tr><th scope="col" className="py-2">Cấu hình</th><th scope="col">Occupied IoU</th><th scope="col">Object IoU</th><th scope="col">p95 CPU ms</th></tr></thead>
      <tbody>{ids.map(id => { const m = report!.test_results[id]; return <tr key={id} className={id === "ppo" ? "font-semibold" : ""}>
        <th scope="row" className="border-t border-[var(--line)] py-2 font-normal">{label(id)}</th>
        <td className="border-t border-[var(--line)]">{pct(m.occupied_iou)}</td><td className="border-t border-[var(--line)]">{pct(m.object_iou)}</td>
        <td className="border-t border-[var(--line)]">{m.latency_p95_ms.toFixed(1)}</td></tr>; })}</tbody>
    </table></div>;
  }
  return <details className="agent-review" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer py-3 font-semibold">Học tăng cường · 12 cấu hình LiDAR CARLA</summary>
    {error && <div role="alert"><p className="agent-error">{error}</p><Button variant="secondary" onClick={() => setAttempt(v => v + 1)}>Kiểm tra lại</Button></div>}
    {!data && !error && open && <p className="agent-small" role="status">Đang kiểm tra evidence native…</p>}
    {data && !data.ready && <div className="grid gap-2">
      <strong>{phases[data.phase] ?? "Chưa có báo cáo native hoàn tất"}</strong>
      {data.completed != null && data.total != null && <>
        <progress className="h-2 w-full accent-[var(--accent)]" value={data.completed} max={data.total} aria-label="Tiến độ capture native RL" />
        <p className="agent-small">{data.completed}/{data.total} capture thành công{data.frame_progress ? ` · lượt hiện tại ${data.frame_progress.completed}/${data.frame_progress.total} frame` : ""}</p>
      </>}
      {!!data.failed_retries && <p className="agent-small">Đã thử lại một lỗi native; lượt lỗi gốc được giữ trong evidence.</p>}
      <p className="agent-small">{data.notice} Không dùng pilot một route để thay tập train/test.</p>
    </div>}
    {report && <div className="grid gap-3">
      <p className="agent-small">Town01 · 2 route train / 1 validation / 1 test · {report.actual_steps.toLocaleString("vi-VN")} bước cập nhật PPO · checkpoint chọn ở bước {report.selected_policy_trained_steps.toLocaleString("vi-VN")}</p>
      <div className="border-l-2 border-[var(--accent)] pl-3"><strong>{report.no_improvement_over_full ? "Chưa tốt hơn cấu hình mặc định" : "Reward cao hơn mặc định trên route test này"}</strong>
        <p className="agent-small">{report.no_improvement_over_full ? "Giữ cấu hình mặc định; báo kết quả thật thay vì ép agent đổi sensor." : "Chưa đủ để dùng ngoài mô phỏng. Cần thêm route chưa thấy và kiểm tra chuyển sensor online."}</p></div>
      {rows(["fixed_07", "ppo"])}
      <details><summary className="cursor-pointer py-2 text-xs">Đối chiếu đủ 12 cấu hình cố định</summary>{rows(Object.keys(report.test_results).filter(id => id !== "ppo"))}</details>
      <p className="agent-small">Action áp dụng cho frame kế tiếp. PPO đổi cấu hình {report.test_results.ppo.switches} lần. IoU chỉ chấm ô reference đã quan sát; CPU đo feature + model, chưa gồm mô phỏng hoặc quyết định agent.</p>
      <p className="agent-small">{Object.entries(report.test_results.ppo.action_counts).filter(([, count]) => count > 0).map(([action, count]) => `${label(`fixed_${action.padStart(2, "0")}`)}: ${count} frame`).join(" · ")}</p>
      <details><summary className="cursor-pointer py-2 text-xs">Nguồn và giới hạn nghiên cứu</summary>
        <code className="block break-all text-[10px]">Dataset: {report.dataset_sha256}</code><code className="block break-all text-[10px]">Checkpoint: {report.checkpoint_sha256}</code>
        {data?.ready && <code className="block break-all text-[10px]">Report: {data.evidence_sha256}</code>}
        <ul className="list-disc pl-4 text-xs">{report.limitations.map(item => <li key={item}>{item}</li>)}</ul>
      </details>
      <a className="agent-tools-button" href={`${base}/report`} download>Tải báo cáo native PPO ↓</a>
    </div>}
  </details>;
}
