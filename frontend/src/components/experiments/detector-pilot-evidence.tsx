"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { apiJson } from "@/lib/lab-api";

const base = "/api/v1/experiments/detector-pilot";
type Variant = { variant: string; frames: number; wall_mean_ms: number; wall_p95_ms: number;
  cuda_activity_mean_ms: number; matched_target_frame_instances: number; target_frame_instances: number;
  checkpoint_sha256: string; resolved_config_sha256: string; report_url: string; geometry_url: string;
  period_exceedance_fraction: Record<string, number> };
type Evidence = { available: boolean; evidence_sha256: string; conclusion: string; variants: Variant[];
  bundle_manifest_sha256: string; limitations: string[] };
type Review = { id: string; reviewer: string; notes: string; verdict: string };
const names: Record<string, string> = { "lidar-full-fp32": "LiDAR · đủ điểm", "lidar-half-fp32": "LiDAR · 50% điểm",
  "lidar-full-amp": "LiDAR · AMP", "cl-full-fp32": "Camera + LiDAR", "cl-full-amp": "Camera + LiDAR · AMP" };

export default function DetectorPilotEvidence() {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [verdict, setVerdict] = useState("needs_evidence");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void apiJson<Evidence>(base, controller.signal).then(async value => {
      if (controller.signal.aborted) return;
      setEvidence(value);
      if (value.available) {
        const feedback = await apiJson<{ items: Review[] }>(`${base}/reviews`, controller.signal);
        if (!controller.signal.aborted) setReviews(feedback.items);
      }
    }).catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, []);

  const save = async () => {
    if (!evidence) return;
    setBusy(true); setSaved(false); setError("");
    try {
      const response = await fetch(`${base}/reviews`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewer, notes, verdict, evidence_sha256: evidence.evidence_sha256 }) });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "Không lưu được review.");
      setReviews(previous => [value as Review, ...previous]); setNotes(""); setSaved(true);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };

  return <section className="agent-section" aria-label="Bằng chứng detector trên GPU">
    <details>
      <summary>Detector trên GPU · pilot 20 frame</summary>
      {error && <p className="agent-error" role="alert">{error.replace(/^Error: /, "")}</p>}
      {!evidence && !error && <p className="agent-small" role="status">Đang lấy evidence đã lưu…</p>}
      {evidence && !evidence.available && <p className="agent-small">Server này chưa chứa bộ evidence detector. Các thí nghiệm occupancy bên trên vẫn dùng được.</p>}
      {evidence?.available && <>
        <p>{evidence.conclusion}</p>
        <p className="agent-small">Runtime BEVFusion OpenMMLab riêng; không dùng các metric precomputed cũ của Lab.</p>
        <p className="agent-small">Town01 · clear · seed 7 · RTX 2050. Cùng một capture, 20 frame liên tiếp. Ghép tâm trong 2 m với GT actor được spawn; đây là chẩn đoán hình học, chưa phải mAP hoặc precision toàn cảnh.</p>
        <div className="agent-pilot-table" role="region" aria-label="So sánh 5 cấu hình detector" tabIndex={0}>
          <table><caption>Đo sau warmup, CARLA dừng trong lúc inference</caption>
            <thead><tr><th scope="col">Cấu hình</th><th scope="col">Wall TB</th><th scope="col">CUDA TB</th><th scope="col">Ghép mục tiêu¹</th></tr></thead>
            <tbody>{evidence.variants.map(row => <tr key={row.variant}><th scope="row">{names[row.variant] ?? row.variant}</th><td>{row.wall_mean_ms.toFixed(1)} ms</td><td>{row.cuda_activity_mean_ms.toFixed(1)} ms</td><td>{row.matched_target_frame_instances}/{row.target_frame_instances}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="agent-small">¹ Mục tiêu/frame có tương quan, GT chỉ phủ actor đã spawn. Không tính false positive từ GT thiếu. CUDA là activity của detector trong pass đo riêng; chưa gồm monitoring/chuyển profile hoặc tổng GPU work/window.</p>
        {evidence.variants.map(row => <details key={row.variant} className="agent-trial"><summary>{names[row.variant] ?? row.variant} · reference & nhịp chạy</summary>
          <p className="agent-small">p95 wall {row.wall_p95_ms.toFixed(1)} ms. Vượt chu kỳ 5/10/20 Hz: {[5, 10, 20].map(hz => `${(row.period_exceedance_fraction[String(hz)] * 100).toFixed(0)}%`).join(" / ")}. Chưa tính đồng bộ online.</p>
          <dl className="agent-provenance"><dt>Checkpoint SHA</dt><dd>{row.checkpoint_sha256}</dd><dt>Config SHA</dt><dd>{row.resolved_config_sha256}</dd></dl>
          <div className="agent-trial-actions"><a href={row.report_url} target="_blank" rel="noreferrer">Run JSON ↗</a><a href={row.geometry_url} target="_blank" rel="noreferrer">Ghép GT ↗</a></div>
        </details>)}
        <p className="agent-small">Reference bundle SHA: <span className="agent-hash">{evidence.bundle_manifest_sha256}</span></p>
        <a className="agent-text-button" href={base} target="_blank" rel="noreferrer">Mở bảng evidence JSON ↗</a>
        <form className="agent-review" onSubmit={event => { event.preventDefault(); void save(); }}>
          <h3>Engineer review · detector</h3>
          <p className="agent-small">Review gắn với snapshot này, không tự train lại hoặc đổi cấu hình. Tên người đánh giá là tự khai báo.</p>
          <label>Tên engineer<input required maxLength={80} value={reviewer} onChange={event => setReviewer(event.target.value)} /></label>
          <label>Đánh giá<select value={verdict} onChange={event => setVerdict(event.target.value)}><option value="needs_evidence">Cần thêm bằng chứng</option><option value="accept">Đồng ý với kết luận</option><option value="reject">Không đồng ý</option></select></label>
          <label>Lý do<textarea required minLength={10} maxLength={2000} rows={3} value={notes} onChange={event => setNotes(event.target.value)} /></label>
          <Button loading={busy} disabled={!reviewer.trim() || notes.trim().length < 10}>Lưu review detector</Button>
          {saved && <p role="status">Đã lưu review cùng snapshot evidence.</p>}
        </form>
        {reviews.map(review => <details key={review.id}><summary>{review.reviewer} · {({ accept: "Đồng ý", reject: "Không đồng ý", needs_evidence: "Cần bằng chứng" } as Record<string, string>)[review.verdict]}</summary><p>{review.notes}</p></details>)}
      </>}
    </details>
  </section>;
}
