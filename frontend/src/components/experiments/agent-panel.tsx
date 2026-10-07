"use client";

import { useEffect, useRef, useState } from "react";
import { apiJson } from "@/lib/lab-api";
import { Button } from "@/components/ui/button";
import { useExperimentSession } from "./use-experiment-session";

const base = "/api/v1/experiments";
type Source = "carla" | "dataset_replay";
type Study = { id: string; source: Source; status: string; total_trials: number;
  metadata: { request?: string }; jobs: { id: string; status: string; profile: string }[];
  summary?: { explanation: string } | null };
export type EvidenceTrial = { job_id: string; profile: string; status: string; iou: number | null;
  cost: number | null; iou_drop: number | null; reduction: number | null; eligible: boolean;
  reasons: string[]; error: string | null; configuration: object; reference_sha256: string | null;
  checkpoint_sha256: string | null; input_sha256: string | null; frame_count: number;
  visible_actor_counts: number[] | null; label_policy: string | null;
  cache_hits: number | null; device: string | null; hardware: string | null;
  latency_model_only_ms: { p95: number } | null; evidence_path: string };
type Decision = { model: string; outcome: string; selected: string | null; explanation: string;
  cost_unit: string; cost_scope: string; trials: EvidenceTrial[] };
type Evidence = { study_id: string; evidence_sha256: string; constraints: { min_occupied_iou: number; max_iou_drop: number };
  environments: { environment: number; scenario: object; decisions: Decision[] }[]; limitations: string[]; notice: string };
type Review = { id: string; reviewer: string; verdict: string; notes: string; created_at: number };
export type Inspection = { baseline: EvidenceTrial; candidate: EvidenceTrial; model: string; session: string;
  study: string; source: Source };
const reasons: Record<string, string> = {
  trial_failed_or_cancelled: "Lượt thử lỗi hoặc đã hủy", reference_mismatch_or_missing: "Tham chiếu không khớp/thiếu",
  missing_measurement: "Thiếu số đo", below_minimum_iou: "IoU dưới ngưỡng tối thiểu",
  quality_drop_exceeds_limit: "Giảm IoU quá mức cho phép",
};
const outcomes: Record<string, string> = { improved: "Có phương án giảm dữ liệu", no_improvement: "Giữ cấu hình gốc", inconclusive: "Chưa đủ bằng chứng" };
const statuses: Record<string, string> = { running: "Đang đo", completed: "Hoàn tất", cancelled: "Đã hủy" };
const pct = (value: number | null) => value == null ? "Chưa đo" : `${(value * 100).toFixed(1)}%`;

export default function AgentPanel({ initialSource, onInspect }: { initialSource: Source; onInspect: (inspection: Inspection) => void }) {
  const { session, error: sessionError, start: startSession, loading: sessionLoading } = useExperimentSession();
  const [source, setSource] = useState<Source>(initialSource);
  const [enabled, setEnabled] = useState(false);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Study[]>([]);
  const [study, setStudy] = useState<Study | null>(null);
  const [report, setReport] = useState<Evidence | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<object | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [verdict, setVerdict] = useState("needs_evidence");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const [explanation, setExplanation] = useState<{ study: string; text: string } | null>(null);
  const current = useRef("");
  const studyId = study?.id;
  const scope = source === "dataset_replay" ? session : "";
  const url = (path: string) => `${base}${path}${scope ? `${path.includes("?") ? "&" : "?"}session=${encodeURIComponent(scope)}` : ""}`;
  const post = async <T,>(path: string, body: unknown = {}): Promise<T> => {
    const response = await fetch(url(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    return data as T;
  };
  const choose = (item: Study) => {
    current.current = item.id; setStudy(item); setReport(null); setReviews([]); setSaved(false); setNotes(""); setError("");
  };

  useEffect(() => {
    if (source === "dataset_replay" && !session) return;
    const controller = new AbortController();
    const suffix = source === "dataset_replay" ? `?session=${encodeURIComponent(session)}` : "";
    const path = source === "dataset_replay" ? "/replay/studies" : "/sensor-agent";
    void Promise.all([apiJson<{ agent_enabled: boolean }>(`${base}/registry`, controller.signal),
      apiJson<{ items: Study[] }>(`${base}${path}${suffix}`, controller.signal)])
      .then(([registry, data]) => {
        if (controller.signal.aborted) return;
        setEnabled(registry.agent_enabled); setHistory(data.items.filter(item => item.source === source));
      }).catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, [source, session]);

  useEffect(() => {
    if (!studyId || (source === "dataset_replay" && !session)) return;
    const id = studyId;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const suffix = source === "dataset_replay" ? `?session=${encodeURIComponent(session)}` : "";
    const poll = async () => {
      try {
        const fresh = await apiJson<Study>(`${base}/sensor-agent/${id}${suffix}`, controller.signal);
        if (controller.signal.aborted) return;
        setStudy(fresh); setHistory(previous => [fresh, ...previous.filter(item => item.id !== id)]);
        if (fresh.status === "completed") {
          const [evidence, feedback] = await Promise.all([
            apiJson<Evidence>(`${base}/sensor-agent/${id}/evidence${suffix}`, controller.signal),
            apiJson<{ items: Review[] }>(`${base}/sensor-agent/${id}/reviews${suffix}`, controller.signal),
          ]);
          if (!controller.signal.aborted) { setReport(evidence); setReviews(feedback.items); }
        } else if (fresh.status === "running") timer = setTimeout(poll, 2500);
      } catch (cause) {
        if (!controller.signal.aborted) { setError(String(cause)); timer = setTimeout(poll, 5000); }
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [studyId, source, session]);

  const send = async (planOnly = false) => {
    setBusy(true); setError(""); setDraft(null);
    try {
      if (planOnly) {
        const data = await post<{ spec: object }>("/plan", { message });
        setDraft(data.spec); window.dispatchEvent(new CustomEvent("p027-agent-plan", { detail: data.spec }));
      } else {
        const item = await post<Study>(source === "carla" ? "/sensor-agent/start" : "/replay/agent/start", { message });
        choose(item); setMessage(""); setHistory(previous => [item, ...previous]);
      }
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const save = async () => {
    if (!report) return;
    const id = report.study_id;
    setBusy(true); setError(""); setSaved(false);
    try {
      const value = await post<Review>(`/sensor-agent/${id}/reviews`, { reviewer, verdict, notes, evidence_sha256: report.evidence_sha256 });
      if (current.current === id) { setReviews(previous => [value, ...previous]); setSaved(true); setNotes(""); }
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const download = () => {
    const blob = new Blob([JSON.stringify({ evidence: report, engineer_reviews: reviews }, null, 2)], { type: "application/json" });
    const href = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = href; anchor.download = `agent-evidence-${report?.study_id}.json`; anchor.click(); URL.revokeObjectURL(href);
  };
  const explain = async () => {
    if (!report) return;
    const id = report.study_id;
    setBusy(true); setError("");
    try {
      const value = await post<{ explanation: string }>(`/sensor-agent/${id}/summarize`);
      if (current.current === id) setExplanation({ study: id, text: value.explanation });
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };
  const running = study?.status === "running" || history.some(item => item.status === "running");
  return <div className="agent-panel-body">
    <div className="agent-source" role="group" aria-label="Nguồn thí nghiệm">
      {(["carla", "dataset_replay"] as const).map(value => <button key={value} disabled={busy} aria-pressed={source === value} onClick={() => {
        setSource(value); setStudy(null); setReport(null); setHistory([]); setReviews([]); setDraft(null); setError(""); current.current = "";
      }}>{value === "carla" ? "CARLA" : "nuScenes replay"}</button>)}
    </div>
    <p className="agent-small">{source === "carla" ? "Mô phỏng CARLA · hiện hỗ trợ occupancy LiDAR." : "Dữ liệu ghi sẵn · LiDAR, radar và chất lượng ảnh."} RL chọn profile chưa được nối vào vòng kín này.</p>
    {!enabled && <p className="agent-notice" role="status">Chưa bật LLM hoặc chưa cấu hình API key. Bạn vẫn xem evidence và dùng form CARLA thủ công được.</p>}
    {source === "dataset_replay" && sessionError && <p role="alert" className="agent-notice">{sessionError}{!session && <Button loading={sessionLoading} onClick={() => void startSession()}>Mở phiên replay mới</Button>}</p>}
    {error && <p role="alert" className="agent-error">{error.replace(/^Error: /, "")}</p>}
    <form className="agent-compose" onSubmit={event => { event.preventDefault(); void send(); }}>
      <label htmlFor="dock-message">Bạn muốn kiểm chứng điều gì?</label>
      <textarea id="dock-message" rows={3} maxLength={2000} value={message} onChange={event => setMessage(event.target.value)} placeholder={source === "carla" ? "So sánh baseline với LiDAR 300.000 và 150.000 điểm/s ở Town01, 2 frame…" : "Thử giữ 50% điểm LiDAR/radar ở scene-0103, 2 frame; IoU giảm tối đa 0.02…"} />
      <Button type="submit" loading={busy} disabled={!enabled || !message.trim() || running || (source === "dataset_replay" && !session)}>Gửi & kiểm chứng</Button>
      {source === "carla" && <button type="button" className="agent-text-button" disabled={busy || !enabled || !message.trim()} onClick={() => void send(true)}>Chỉ lập cấu hình để tôi kiểm tra trước</button>}
      <p className="agent-small">Gửi yêu cầu sẽ tạo lượt đo mới và dùng token LLM. Đọc evidence không gọi LLM.</p>
    </form>
    {draft && <details open><summary>Cấu hình nháp · chưa chạy</summary><p className="agent-small">Nếu đang ở CARLA Lab, cấu hình đã điền vào form. Kiểm tra rồi bấm tạo thí nghiệm.</p><pre>{JSON.stringify(draft, null, 2)}</pre></details>}
    <section className="agent-section" aria-label="Lịch sử và bằng chứng">
      <div className="agent-section-heading"><h3>Evidence</h3><span>Đo trước, kết luận sau</span></div>
      <label className="agent-small">Lượt đánh giá<select aria-label="Lượt đánh giá agent" value={study?.id ?? ""} onChange={event => { const item = history.find(item => item.id === event.target.value); if (item) choose(item); }}><option value="" disabled>Chọn lượt đã chạy</option>{history.map(item => <option key={item.id} value={item.id}>{item.id.slice(0, 8)} · {statuses[item.status] ?? item.status}</option>)}</select></label>
      {!study && <div className="agent-empty"><strong>Chưa chọn lượt đánh giá</strong><p>Tôi không thể khẳng định cấu hình nào tốt hơn khi chưa có số đo cùng tham chiếu. Chọn lịch sử hoặc tạo lượt kiểm chứng.</p></div>}
      {study && <div className="agent-study"><p className="agent-request">{study.metadata.request ?? `Study ${study.id.slice(0, 8)}`}</p><p className="agent-small" role="status">{statuses[study.status] ?? study.status} · {study.jobs.filter(job => ["succeeded", "failed", "cancelled"].includes(job.status)).length}/{study.total_trials} lượt xử lý</p>{study.status === "running" && <Button variant="secondary" loading={busy} onClick={async () => { setBusy(true); try { choose(await post<Study>(`/sensor-agent/${study.id}/cancel`)); } catch (cause) { setError(String(cause)); } finally { setBusy(false); } }}>Hủy lượt đánh giá</Button>}</div>}
      {report && <>
        <p className="agent-small">IoU tối thiểu {pct(report.constraints.min_occupied_iou)} · được giảm tối đa {(report.constraints.max_iou_drop * 100).toFixed(1)} điểm phần trăm.</p>
        {report.environments.map(environment => <div key={environment.environment}>
          <details><summary>Cảnh {environment.environment + 1} · cấu hình môi trường</summary><pre>{JSON.stringify(environment.scenario, null, 2)}</pre></details>
          {environment.decisions.map(decision => {
            const baseline = decision.trials.find(trial => trial.profile === "baseline")!;
            return <article key={decision.model} className="agent-decision" data-outcome={decision.outcome}>
              <p className="agent-small">{decision.model}</p><h4>{outcomes[decision.outcome]}</h4><p>{decision.explanation}</p>
              <div className="agent-measures"><span>Cấu hình gốc<strong>{pct(baseline.iou)} IoU</strong></span><span>Lựa chọn đạt ngưỡng<strong>{decision.selected ?? "Chưa có"}</strong></span></div>
              {decision.trials.map(trial => <details key={trial.job_id} className="agent-trial"><summary><span>{trial.profile === "baseline" ? "Cấu hình gốc" : trial.profile}</span><span>{pct(trial.iou)} · {trial.eligible ? "Đạt ngưỡng" : "Chưa đạt"}</span></summary>
                <p>{trial.cost == null ? "Chi phí dữ liệu chưa đo" : `${trial.cost.toLocaleString("vi-VN")} ${decision.cost_unit}${decision.cost_scope === "estimated_lidar_payload_rate" ? " (ước tính từ payload LiDAR)" : ""}`} · giảm {pct(trial.reduction)} dữ liệu.</p>
                <p className="agent-small">Chênh lệch IoU (gốc − ứng viên): {trial.iou_drop == null ? "chưa đo" : `${(trial.iou_drop * 100).toFixed(2)} điểm phần trăm`}. Đánh giá trên {trial.frame_count} frame{trial.visible_actor_counts ? ` · vật trong ROI: ${trial.visible_actor_counts.join(", ")}` : ""}.</p>
                {trial.reasons.map(reason => <p key={reason} className="agent-error">{reasons[reason] ?? reason}</p>)}{trial.error && <p className="agent-error">{trial.error}</p>}
                <p className="agent-small">p95 model: {trial.latency_model_only_ms?.p95 ?? "Chưa đo"}{trial.latency_model_only_ms ? " ms" : ""} · cache {trial.cache_hits ?? "—"} frame. Giảm bytes không chứng minh giảm GPU.</p>
                <dl className="agent-provenance"><dt>Run</dt><dd>{trial.job_id}</dd><dt>Reference SHA</dt><dd>{trial.reference_sha256 ?? "Thiếu"}</dd><dt>Checkpoint SHA</dt><dd>{trial.checkpoint_sha256 ?? "Thiếu"}</dd><dt>Thiết bị</dt><dd>{trial.device ?? "Chưa ghi"} · {trial.hardware ?? "Chưa ghi"}</dd></dl>
                <details><summary>Thông số thực chạy</summary><pre>{JSON.stringify(trial.configuration, null, 2)}</pre></details>
                {trial.label_policy && <p className="agent-small">Nguồn nhãn: {trial.label_policy}</p>}
                <div className="agent-trial-actions"><a href={url(trial.evidence_path.slice(base.length))} target="_blank" rel="noreferrer">Mở run JSON ↗</a>{trial.status === "succeeded" && baseline.status === "succeeded" && trial.frame_count > 0 && baseline.frame_count > 0 && !trial.reasons.includes("reference_mismatch_or_missing") && <button onClick={() => onInspect({ baseline, candidate: trial, model: decision.model, session: scope, study: report.study_id, source })}>Đối chiếu trên map →</button>}</div>
              </details>)}
            </article>;
          })}
        </div>)}
        <details><summary>Giới hạn của bằng chứng</summary><ul>{report.limitations.map(value => <li key={value}>{value}</li>)}</ul></details>
        <Button variant="secondary" loading={busy} disabled={!enabled} onClick={() => void explain()}>Nhờ agent giải thích · dùng token LLM</Button>
        {(explanation?.study === report.study_id || study?.summary) && <div className="agent-study"><h3>Diễn giải của agent</h3><p className="whitespace-pre-wrap">{explanation?.study === report.study_id ? explanation.text : study?.summary?.explanation}</p><p className="agent-small">Diễn giải LLM không thay đổi lựa chọn của evaluator. Đối chiếu số đo và run JSON phía trên.</p></div>}
        <button className="agent-text-button" onClick={download}>Tải evidence + đánh giá engineer ↓</button>
        <form className="agent-review" onSubmit={event => { event.preventDefault(); void save(); }}>
          <h3>Engineer review</h3><p className="agent-small">Đánh giá kết luận trên evidence này. Phản hồi được lưu để review, chưa tự train lại policy. Tên người đánh giá là tự khai báo.</p>
          <label>Tên engineer<input required maxLength={80} value={reviewer} onChange={event => setReviewer(event.target.value)} /></label>
          <label>Đánh giá<select value={verdict} onChange={event => setVerdict(event.target.value)}><option value="needs_evidence">Cần thêm bằng chứng</option><option value="accept">Đồng ý với kết luận</option><option value="reject">Không đồng ý</option></select></label>
          <label>Lý do / hướng cải thiện<textarea required minLength={10} maxLength={2000} rows={3} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Cần thêm scene đông người, seed khác hoặc đo GPU thực…" /></label>
          <Button loading={busy} disabled={!reviewer.trim() || notes.trim().length < 10}>Lưu đánh giá</Button>
          {saved && <p role="status">Đã lưu cùng snapshot evidence. Không thay đổi kết quả đo.</p>}
        </form>
        {reviews.map(review => <details key={review.id}><summary>{review.reviewer} · {({ accept: "Đồng ý", reject: "Không đồng ý", needs_evidence: "Cần bằng chứng" } as Record<string, string>)[review.verdict]}</summary><p>{review.notes}</p><p className="agent-small">{new Date(review.created_at * 1000).toLocaleString("vi-VN")}</p></details>)}
      </>}
    </section>
  </div>;
}
