"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { apiJson } from "@/lib/lab-api";
import type { Inspection } from "./agent-panel";

function Prediction({ url, label }: { url: string; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [failure, setFailure] = useState<{ url: string; message: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const ctx = canvas.current?.getContext("2d");
    ctx?.clearRect(0, 0, 200, 200);
    void apiJson<{ cells: number[] }>(url, controller.signal).then(data => {
      if (controller.signal.aborted || !ctx) return;
      if (data.cells.length !== 40000) throw new Error("Kích thước BEV không hợp lệ");
      const pixels = ctx.createImageData(200, 200);
      const colors = [[16, 38, 46], [80, 167, 152], [255, 177, 76]];
      data.cells.forEach((value, i) => pixels.data.set([...(colors[value] ?? colors[0]), 255], (39999 - i) * 4));
      ctx.putImageData(pixels, 0, 0);
    }).catch(cause => { if (!controller.signal.aborted) setFailure({ url, message: String(cause) }); });
    return () => controller.abort();
  }, [url]);
  return <><canvas ref={canvas} width={200} height={200} aria-label={label} className="w-full aspect-square [image-rendering:pixelated] bg-[var(--navy)]" />{failure?.url === url && <p role="alert">{failure.message}</p>}</>;
}

export function EvidenceViewport({ inspection, onClose }: { inspection: Inspection; onClose: () => void }) {
  const [frame, setFrame] = useState(0);
  const frameCount = Math.min(inspection.baseline.frame_count, inspection.candidate.frame_count);
  const index = Math.min(frame, Math.max(0, frameCount - 1));
  const url = (job: string, path: string) => `/api/v1/experiments/${job}/${path}${path.includes("?") ? "&" : "?"}${inspection.session ? `session=${encodeURIComponent(inspection.session)}` : ""}`;
  return <section className="evidence-viewport" aria-label="Đối chiếu bằng chứng trên bản đồ">
    <header><div><p className="eyebrow">{inspection.source === "carla" ? "CARLA" : "NUSCENES REPLAY"} / CÙNG THAM CHIẾU / CÙNG CHECKPOINT</p><h1>Cấu hình gốc <span>↔</span> {inspection.candidate.profile}</h1><p>{inspection.model} · Study {inspection.study.slice(0, 8)}</p></div><button onClick={onClose}>Quay lại workspace ↗</button></header>
    <div className="evidence-frame-control"><label htmlFor="evidence-frame">Frame {index + 1}/{frameCount}</label><input id="evidence-frame" type="range" min={0} max={Math.max(0, frameCount - 1)} value={index} onChange={event => setFrame(Number(event.target.value))} /><span>Phía trước ↑ · static xanh · object cam</span></div>
    <div className="evidence-map-pair">{[inspection.baseline, inspection.candidate].map((trial, side) => <figure key={side}>
      <figcaption><strong>{side === 0 ? "Cấu hình gốc" : trial.profile}</strong><span>IoU {trial.iou == null ? "chưa đo" : `${(trial.iou * 100).toFixed(1)}%`}</span></figcaption>
      <Prediction url={url(trial.job_id, `predictions/${inspection.model}/${index}`)} label={`${side === 0 ? "Baseline" : "Ứng viên"} occupancy frame ${index}`} />
      <details><summary>Ảnh camera cùng frame</summary><Image unoptimized width={640} height={360} src={url(trial.job_id, `camera?index=${index}`)} alt={`Ảnh camera ${trial.profile}, frame ${index}`} className="w-full h-auto" /></details>
      <p className="agent-small">Run {trial.job_id}</p>
    </figure>)}</div>
    <p className="evidence-footnote">Đây là occupancy 2D từ checkpoint, không phải Seg3D. Ô thay đổi không đồng nghĩa ô sai. Kết luận dựa trên các frame đã đo; xem reference, ngưỡng và giới hạn trong panel agent.</p>
  </section>;
}
