"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/lab-api";
import { Button } from "@/components/ui/button";
import type { EvidenceTrial, Inspection } from "./agent-panel";

type Profile = {
  profile: string;
  job_id: string;
  channels: number;
  points_per_second: number;
  frames: number;
  sampled_lidar_bytes_per_second: number;
  metrics: { occupied_iou: number; object_recall: number; class_iou: { object: number } };
};
type Report = {
  profiles: Profile[];
  limitations: string[];
  study_evidence: {
    study_id: string;
    environments: { decisions: { trials: EvidenceTrial[] }[] }[];
  }[];
};
type Evidence =
  | { ready: false; notice: string }
  | { ready: true; evidence_sha256: string; report: Report };

const channels = [16, 32, 64];
const rates = [150, 300, 450, 600];
const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

function comparisonFor(report: Report, job: string): Inspection | null {
  for (const study of report.study_evidence) {
    for (const environment of study.environments) {
      for (const decision of environment.decisions) {
        const baseline = decision.trials.find(trial => trial.profile === "baseline");
        const candidate = decision.trials.find(trial => trial.job_id === job);
        if (baseline && candidate && baseline.job_id !== candidate.job_id) {
          return { baseline, candidate, model: "occupancy_lidar", session: "", study: study.study_id, source: "carla" };
        }
      }
    }
  }
  return null;
}

export function NativeProfileEvidence({ onInspect }: { onInspect: (inspection: Inspection) => void }) {
  const [data, setData] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState("channels32_600k");

  useEffect(() => {
    const controller = new AbortController();
    void apiJson<Evidence>("/api/v1/experiments/native-profile-pilot", controller.signal)
      .then(setData)
      .catch(cause => { if (!controller.signal.aborted) setError(String(cause)); });
    return () => controller.abort();
  }, [attempt]);

  const current = data?.ready ? data.report.profiles.find(profile => profile.profile === selected) : null;
  const comparison = data?.ready && current ? comparisonFor(data.report, current.job_id) : null;

  return <details className="agent-trial">
    <summary>12 profile LiDAR · pilot đã đo</summary>
    {error && <div role="alert" className="agent-error">
      <p>{error}</p>
      <Button variant="secondary" onClick={() => { setError(""); setData(null); setAttempt(value => value + 1); }}>
        Đọc lại evidence
      </Button>
    </div>}
    {!data && !error && <p role="status" className="agent-small">Đang đọc evidence…</p>}
    {data && !data.ready && <p className="agent-small">{data.notice}</p>}
    {data?.ready && <>
      <p className="agent-small">Occupied IoU · cùng reference, 4 frame/profile. Chọn ô để xem riêng chất lượng vật thể.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-center text-xs tabular-nums">
          <caption className="sr-only">So sánh profile LiDAR theo số kênh và điểm mỗi giây</caption>
          <thead><tr>
            <th scope="col" className="p-2 text-left">Kênh</th>
            {rates.map(rate => <th scope="col" className="p-2" key={rate}>{rate}k</th>)}
          </tr></thead>
          <tbody>{channels.map(channel => <tr key={channel}>
            <th scope="row" className="p-2 text-left">{channel}</th>
            {rates.map(rate => {
              const profile = data.report.profiles.find(item => item.channels === channel && item.points_per_second === rate * 1000)!;
              const active = selected === profile.profile;
              return <td key={rate} className="p-1">
                <button type="button" aria-pressed={active}
                  aria-label={`LiDAR ${channel} kênh, ${rate}k điểm/s, occupied IoU ${pct(profile.metrics.occupied_iou)}`}
                  onClick={() => setSelected(profile.profile)}
                  className={`w-full rounded px-2 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${active ? "bg-[var(--navy)] text-white" : "bg-[var(--surface-subtle)] text-[var(--foreground)] hover:bg-[var(--line)]"}`}>
                  {pct(profile.metrics.occupied_iou)}
                </button>
              </td>;
            })}
          </tr>)}</tbody>
        </table>
      </div>
      {current && <div className="grid gap-2 border-t border-[var(--line)] pt-3" aria-live="polite">
        <strong className="text-sm">{current.channels} kênh · {current.points_per_second / 1000}k điểm/s</strong>
        <p className="agent-small">Object IoU {pct(current.metrics.class_iou.object)} · object-cell recall {pct(current.metrics.object_recall)}.</p>
        <p className="agent-small">Payload lấy mẫu {(current.sampled_lidar_bytes_per_second / 1e6).toFixed(2)} MB/s; không là chi phí GPU hoặc tiền.</p>
        <a className="agent-text-button" href={`/api/v1/experiments/${current.job_id}`} target="_blank" rel="noreferrer">
          Mở run và cấu hình thực chạy ↗
        </a>
        {comparison && <Button variant="secondary" onClick={() => onInspect(comparison)}>Đối chiếu trên map →</Button>}
      </div>}
      <p className="agent-small">Một route Town01; căn chỉnh intensity thử nghiệm. Chưa đủ train/validation/test native, chưa nối 12 profile này vào PPO hoặc chứng minh an toàn thực tế.</p>
      <details>
        <summary>Nguồn và giới hạn</summary>
        <p className="break-all font-mono text-xs">SHA {data.evidence_sha256}</p>
        <ul className="list-disc pl-4">{data.report.limitations.map(limit => <li key={limit} className="agent-small">{limit}</li>)}</ul>
      </details>
      <a className="agent-text-button" href="/api/v1/experiments/native-profile-pilot/report" download>Tải audit 12 profile ↓</a>
    </>}
  </details>;
}
