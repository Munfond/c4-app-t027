"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { apiJson } from "@/lib/lab-api";
import { Button } from "@/components/ui/button";
import type { Inspection } from "./agent-panel";

type Side = { cells: number[]; image: string | null; cameraError: string | null };
type Pair = { index: number; sides: [Side, Side] };
const release = (pair: Pair) => pair.sides.forEach(side => { if (side.image) URL.revokeObjectURL(side.image); });

function Prediction({ cells, label }: { cells?: number[]; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || !cells) return;
    const pixels = ctx.createImageData(200, 200);
    const colors = [[16, 38, 46], [80, 167, 152], [255, 177, 76]];
    cells.forEach((value, i) => pixels.data.set([...(colors[value] ?? colors[0]), 255], (39999 - i) * 4));
    ctx.putImageData(pixels, 0, 0);
  }, [cells]);
  return <canvas ref={canvas} width={200} height={200} aria-label={label} className="w-full aspect-square [image-rendering:pixelated] bg-[var(--navy)]" />;
}

export function EvidenceViewport({ inspection, onClose }: { inspection: Inspection; onClose: () => void }) {
  const [desired, setDesired] = useState(0);
  const [pair, setPair] = useState<Pair | null>(null);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const cache = useRef(new Map<number, Pair>());
  const pending = useRef(new Map<number, Promise<Pair>>());
  const controllers = useRef(new Set<AbortController>());
  const shown = useRef<number | null>(null);
  const alive = useRef(true);
  const baseline = inspection.baseline.job_id;
  const candidate = inspection.candidate.job_id;
  const model = inspection.model;
  const session = inspection.session;
  const frameCount = Math.min(inspection.baseline.frame_count, inspection.candidate.frame_count);
  const index = Math.min(desired, Math.max(0, frameCount - 1));

  useEffect(() => {
    alive.current = true;
    const stored = cache.current;
    const requests = controllers.current;
    return () => { alive.current = false; requests.forEach(controller => controller.abort()); stored.forEach(release); stored.clear(); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const url = (job: string, path: string) => `/api/v1/experiments/${job}/${path}${session ? `${path.includes("?") ? "&" : "?"}session=${encodeURIComponent(session)}` : ""}`;
    const load = (target: number): Promise<Pair> => {
      const cached = cache.current.get(target);
      if (cached) return Promise.resolve(cached);
      const underway = pending.current.get(target);
      if (underway) return underway;
      const controller = new AbortController();
      controllers.current.add(controller);
      const createdImages: string[] = [];
      const task = (async () => {
        try {
        const sides = await Promise.all([baseline, candidate].map(async job => {
          const [prediction, camera] = await Promise.all([
            apiJson<{ cells: number[] }>(url(job, `predictions/${encodeURIComponent(model)}/${target}`), controller.signal),
            fetch(url(job, `camera?index=${target}`), { signal: controller.signal }).then(async response => {
              if (!response.ok) return { blob: null, error: `Camera HTTP ${response.status}` };
              return { blob: await response.blob(), error: null };
            }),
          ]);
          if (prediction.cells.length !== 40000 || prediction.cells.some(value => !Number.isInteger(value) || value < 0 || value > 2)) throw new Error("Lưới BEV không hợp lệ");
          if (controller.signal.aborted) throw new Error("Đã đóng đối chiếu");
          const image = camera.blob ? URL.createObjectURL(camera.blob) : null;
          if (image) {
            createdImages.push(image);
            try { const decoded = new window.Image(); decoded.src = image; await decoded.decode(); }
            catch (cause) { URL.revokeObjectURL(image); throw cause; }
          }
          return { cells: prediction.cells, image, cameraError: camera.error };
        }));
        const ready: Pair = { index: target, sides: sides as [Side, Side] };
        if (!alive.current || controller.signal.aborted) { release(ready); throw new Error("Đã đóng đối chiếu"); }
        cache.current.set(target, ready);
        for (const [key, old] of cache.current) {
          if (cache.current.size <= 6) break;
          if (key !== shown.current && key !== target && key !== index) { release(old); cache.current.delete(key); }
        }
        return ready;
        } catch(cause) { controller.abort();createdImages.forEach(image=>URL.revokeObjectURL(image));throw cause; }
      })();
      pending.current.set(target, task);
      void task.finally(() => { pending.current.delete(target); controllers.current.delete(controller); }).catch(() => {});
      return task;
    };
    void load(index).then(ready => {
      if (!cancelled) { shown.current = ready.index; setPair(ready); setError(""); }
      if (index + 1 < frameCount) void load(index + 1).catch(() => {});
    }).catch(cause => { if (!cancelled) { setError(String(cause)); setPlaying(false); } });
    return () => { cancelled = true; };
  }, [baseline, candidate, model, session, index, frameCount, retry]);

  useEffect(() => {
    if (!playing || error || pair?.index !== index || frameCount < 2 || (index === frameCount - 1 && !loop)) return;
    const timer = setTimeout(() => setDesired(index === frameCount - 1 ? 0 : index + 1), 500);
    return () => clearTimeout(timer);
  }, [playing, error, pair, index, frameCount, loop]);

  const end = index === frameCount - 1;
  const isPlaying = playing && (!end || loop);
  return <section className="evidence-viewport" aria-label="Đối chiếu bằng chứng trên bản đồ">
    <header>
      <div><p className="eyebrow">{inspection.source === "carla" ? "CARLA" : "NUSCENES REPLAY"} / CÙNG THAM CHIẾU / CÙNG CHECKPOINT</p>
        <h1>Cấu hình gốc <span>↔</span> {inspection.candidate.profile}</h1><p>{model} · Study {inspection.study.slice(0, 8)}</p>
      </div><button onClick={onClose}>Quay lại workspace ↗</button>
    </header>
    <div className="evidence-frame-control">
      <Button disabled={!pair || !!error || frameCount < 2} onClick={() => { if (isPlaying) setPlaying(false); else { if (end) setDesired(0); setPlaying(true); } }}>{isPlaying ? "Tạm dừng" : end ? "Phát lại" : "Phát"}</Button>
      <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={loop} onChange={event => setLoop(event.target.checked)} />Lặp</label>
      <label htmlFor="evidence-frame">{pair ? `Frame ${pair.index + 1}/${frameCount}` : "Chuẩn bị cặp frame"}{pair && pair.index !== index ? " · Đồng bộ" : ""}</label>
      <input id="evidence-frame" type="range" min={0} max={Math.max(0, frameCount - 1)} value={index} onChange={event => { setPlaying(false); setDesired(Number(event.target.value)); }} />
      <span>Phát lại 2 frame/s · phía trước ↑ · static xanh · object cam</span>
    </div>
    {error && <div role="alert" className="agent-error">{error} · Giữ cặp frame trước.<Button variant="secondary" onClick={() => setRetry(value => value + 1)}>Thử lại</Button></div>}
    <div className="evidence-map-pair">{[inspection.baseline, inspection.candidate].map((trial, side) => {
      const data = pair?.sides[side];
      return <figure key={side}>
        <figcaption><strong>{side === 0 ? "Cấu hình gốc" : trial.profile}</strong><span>IoU {trial.iou == null ? "chưa đo" : `${(trial.iou * 100).toFixed(1)}%`}</span></figcaption>
        <Prediction cells={data?.cells} label={`${side === 0 ? "Baseline" : "Ứng viên"} occupancy frame ${pair?.index ?? 0}`} />
        <details><summary>Ảnh camera cùng frame</summary>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {data?.image && <img src={data.image} alt={`Camera ${trial.profile}, frame ${(pair?.index ?? 0) + 1}`} className="w-full h-auto" />}
          {data?.cameraError && <p className="agent-error">{data.cameraError} · Không thay bằng ảnh thô hoặc frame khác.</p>}
        </details><p className="agent-small">Run {trial.job_id}</p>
      </figure>;
    })}</div>
    <p className="evidence-footnote">Hai output và ảnh được đồng bộ trước khi đổi frame. Đây là occupancy 2D từ checkpoint, không phải Seg3D. Ô thay đổi chưa đồng nghĩa ô sai; xem reference, ngưỡng và giới hạn trong bot.</p>
  </section>;
}
