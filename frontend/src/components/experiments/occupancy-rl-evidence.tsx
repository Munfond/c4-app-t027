"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/lab-api";
import { Button } from "@/components/ui/button";

type Metrics = { frames: number; occupied_iou: number | null; object_iou: number | null; latency_p95_ms: number;
  deadline_misses: number; action_counts: Record<string, number> };
type Report = { algorithm: string; actual_steps: number; ppo_epoch_updates: number; deadline_ms: number;
  no_improvement_over_full: boolean; results: Record<string, Metrics>; split_scenes: Record<string, string[]>;
  dataset_sha256: string; checkpoint_sha256: string; selected_policy: string; limitations: string[] };
type Evidence = { ready: false; notice: string } | { ready: true; report: Report; evidence_sha256: string; policy_file_sha256: string };
type Review = { id: string; reviewer: string; verdict: string; notes: string };
const base = "/api/v1/experiments/occupancy-rl";
const labels: Record<string,string> = { fixed_full: "Giữ 100%", fixed_half: "Giữ 50%", fixed_quarter: "Giữ 25%", rule: "Rule", ppo: "PPO" };
const pct = (v: number | null) => v == null ? "—" : `${(v * 100).toFixed(1)}%`;

export default function OccupancyRlEvidence() {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [verdict, setVerdict] = useState("needs_evidence");
  const [reviews, setReviews] = useState<Review[]>([]);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const value = await apiJson<Evidence>(base, controller.signal);
        if (controller.signal.aborted) return;
        setEvidence(value); setError("");
        if (value.ready) {
          const rows = await apiJson<{items: Review[]}>(`${base}/reviews`, controller.signal);
          if (!controller.signal.aborted) setReviews(rows.items);
        } else timer = setTimeout(load, 5000);
      } catch (cause) { if (!controller.signal.aborted) setError(String(cause)); }
    };
    void load();
    return () => {controller.abort();clearTimeout(timer);};
  }, []);
  const report = evidence?.ready ? evidence.report : null;
  return <details className="agent-review" aria-label="Học tăng cường có evidence">
    <summary className="cursor-pointer py-3 font-semibold">Học tăng cường · PPO offline</summary>
    {error && <p role="alert" className="agent-error">{error}</p>}
    {!report ? <p className="agent-small">{evidence && !evidence.ready ? evidence.notice : "Đang kiểm tra báo cáo…"}</p> : <div className="grid gap-3">
      <p className="agent-small">nuScenes · {report.split_scenes.test.length} scene test · {report.results.ppo.frames} frame · {report.actual_steps.toLocaleString("vi-VN")} bước PPO</p>
      <div className="border-l-2 border-[var(--accent)] pl-3">
        <strong>{report.no_improvement_over_full ? "Giữ LiDAR đầy đủ" : "PPO có proxy reward cao hơn baseline"}</strong>
        <p className="agent-small">{report.no_improvement_over_full ? "Policy học chọn 100% điểm; chưa tìm thấy cấu hình tốt hơn trong ba mức đã thử. Giảm điểm làm chất lượng giảm, nhưng thời gian chạy model thay đổi ít." : "Kết quả chỉ áp dụng cho replay này; cần kiểm chứng thêm trước khi dùng ngoài mô phỏng."}</p>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs tabular-nums">
        <caption className="pb-2 text-left text-[var(--muted)]">So cùng {report.results.ppo.frames} frame test · IoU theo nhãn occupancy proxy</caption>
        <thead><tr><th className="py-2">Cấu hình</th><th className="py-2">Occupied IoU</th><th className="py-2">Object IoU</th><th className="py-2">p95 ms</th></tr></thead>
        <tbody>{Object.entries(report.results).map(([id,m]) => <tr key={id} className={id === "ppo" ? "font-semibold" : ""}>
          <td className="border-t border-[var(--line)] py-2">{labels[id] ?? id}</td><td className="border-t border-[var(--line)]">{pct(m.occupied_iou)}</td><td className="border-t border-[var(--line)]">{pct(m.object_iou)}</td><td className="border-t border-[var(--line)]">{m.latency_p95_ms.toFixed(1)}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="agent-small">p95 đo tiền xử lý điểm + model trên CPU, dùng lại trong replay; chưa bao gồm thời gian ra quyết định PPO. Ngưỡng {report.deadline_ms} ms theo keyframe, không phải ngưỡng an toàn ADAS.</p>
      <p className="agent-small">PPO chọn: 100% ở {report.results.ppo.action_counts["0"]} frame · 50% ở {report.results.ppo.action_counts["1"]} · 25% ở {report.results.ppo.action_counts["2"]}. Trễ ngưỡng: {report.results.ppo.deadline_misses}.</p>
      <details><summary className="cursor-pointer text-xs">Nguồn, split và giới hạn</summary>
        <p className="agent-small">Train {report.split_scenes.train.length} scene · validation {report.split_scenes.validation.length} · test {report.split_scenes.test.length}. Nhãn static là proxy từ LiDAR; chưa chứng minh khả năng thích nghi ngoài đời hoặc CARLA online.</p>
        <code className="block break-all text-[10px]">Dataset: {report.dataset_sha256}</code>
        <code className="block break-all text-[10px]">Checkpoint: {report.checkpoint_sha256}</code>
        {evidence?.ready && <code className="block break-all text-[10px]">Report: {evidence.evidence_sha256}</code>}
        <ul className="list-disc pl-4 text-xs">{report.limitations.map(item => <li key={item}>{item}</li>)}</ul>
      </details>
      <a className="agent-tools-button" href={`${base}/report`} download>Tải báo cáo đo & đánh giá ↓</a>
      <form className="grid gap-2" onSubmit={async event => {
        event.preventDefault(); if (!evidence?.ready) return;
        setBusy(true);setError("");setSaved(false);
        try {
          const response = await fetch(`${base}/reviews`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({evidence_sha256:evidence.evidence_sha256,reviewer,verdict,notes})});
          const data = await response.json(); if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
          setReviews(previous=>[data,...previous]);setSaved(true);setNotes("");
        } catch (cause) {setError(String(cause));} finally {setBusy(false);}
      }}>
        <strong className="text-sm">Engineer review</strong>
        <label className="text-xs">Tên engineer<input className="mt-1 w-full rounded border border-[var(--line)] p-2" value={reviewer} maxLength={80} onChange={event=>setReviewer(event.target.value)} /></label>
        <label className="text-xs">Đánh giá<select className="mt-1 w-full rounded border border-[var(--line)] p-2" value={verdict} onChange={event=>setVerdict(event.target.value)}><option value="needs_evidence">Cần thêm evidence</option><option value="accept">Đồng ý</option><option value="reject">Không đồng ý</option></select></label>
        <label className="text-xs">Nhận xét<textarea className="mt-1 w-full rounded border border-[var(--line)] p-2" value={notes} maxLength={2000} onChange={event=>setNotes(event.target.value)} /></label>
        <Button loading={busy} disabled={!reviewer.trim() || notes.trim().length < 10}>Lưu review</Button>
        <p className="agent-small">Tên là tự khai báo. Review gắn với SHA báo cáo; chưa tự train lại policy.</p>
        {saved && <p role="status">Đã lưu review.</p>}
      </form>
      {reviews.map(row=><p key={row.id} className="agent-small"><strong>{row.reviewer}</strong> · {row.notes}</p>)}
    </div>}
  </details>;
}
