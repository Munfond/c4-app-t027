"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { apiJson } from "@/lib/lab-api";

type Frame = { index: number; cells: number[]; image: string | null };
export function CapturePlayback({ job, model, count, interval, camera, active, timestamps }: {
  job: string; model: string; count: number; interval: number; camera: boolean; active: boolean; timestamps?: number[];
}) {
  const [index, setIndex] = useState(0);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const cache = useRef(new Map<number, Frame>());
  const pending = useRef(new Map<number, Promise<Frame>>());
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    const entries = cache.current;
    return () => { alive.current = false; entries.forEach(f => { if (f.image) URL.revokeObjectURL(f.image); }); entries.clear(); };
  }, []);
  useEffect(() => {
    let cancelled = false;
    async function load(target: number): Promise<Frame> {
      const cached = cache.current.get(target);
      if (cached) return cached;
      const underway = pending.current.get(target);
      if (underway) return underway;
      const task = (async () => {
        const [data, blob] = await Promise.all([
          apiJson<{ cells: number[] }>(`/api/v1/experiments/${job}/predictions/${encodeURIComponent(model)}/${target}`),
          camera ? fetch(`/api/v1/experiments/${job}/camera?index=${target}`).then(async r => {
            if (!r.ok) throw new Error(`Camera HTTP ${r.status}`);
            return r.blob();
          }) : Promise.resolve(null),
        ]);
        if (data.cells.length !== 40000) throw new Error("Lưới occupancy không hợp lệ");
        const image = blob ? URL.createObjectURL(blob) : null;
        if (image) {
          try { const img = new window.Image(); img.src = image; await img.decode(); }
          catch (cause) { URL.revokeObjectURL(image); throw cause; }
        }
        if (!alive.current) { if (image) URL.revokeObjectURL(image); throw new Error("Preview closed"); }
        const ready = { index: target, cells: data.cells, image };
        cache.current.set(target, ready);
        for (const [key, old] of cache.current) {
          if (cache.current.size <= 6) break;
          if (key !== index && key !== target && key !== frame?.index) {
            if (old.image) URL.revokeObjectURL(old.image);
            cache.current.delete(key);
          }
        }
        return ready;
      })();
      pending.current.set(target, task);
      try { return await task; } finally { pending.current.delete(target); }
    }
    void load(index).then(ready => {
      if (cancelled) return;
      setFrame(ready); setError("");
      if (index + 1 < count) void load(index + 1).catch(() => {});
    }).catch(cause => { if (!cancelled) { setError(String(cause)); setPlaying(false); } });
    return () => { cancelled = true; };
    // Displayed frame is intentionally retained while the requested pair loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job, model, index, count, camera, retry]);
  const measuredGap = timestamps && timestamps[index + 1] - timestamps[index];
  const nextGap = measuredGap && Number.isFinite(measuredGap) && measuredGap > 0 ? measuredGap : interval;
  useEffect(() => {
    if (!playing || !active || error || frame?.index !== index || index === count - 1) return;
    const timer = setTimeout(() => setIndex(index + 1), Math.max(80, nextGap * 1000 / speed));
    return () => clearTimeout(timer);
  }, [playing, active, error, frame, index, count, nextGap, speed]);
  useLayoutEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || !frame) return;
    const pixels = ctx.createImageData(200, 200);
    const colors = [[16, 38, 46], [80, 167, 152], [255, 177, 76]];
    frame.cells.forEach((v, cell) => pixels.data.set([...(colors[v] ?? colors[0]), 255], ((199 - Math.floor(cell / 200)) * 200 + 199 - cell % 200) * 4));
    ctx.putImageData(pixels, 0, 0);
    ctx.strokeStyle = "rgba(255,255,255,.2)"; ctx.lineWidth = .4;
    for (const radius of [20, 50]) {
      ctx.beginPath(); ctx.arc(100,100,radius,0,Math.PI*2);ctx.stroke();
    }
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = .8;
    ctx.beginPath(); ctx.moveTo(96,100);ctx.lineTo(104,100);ctx.moveTo(100,96);ctx.lineTo(100,104);ctx.stroke();
  }, [frame]);
  const end = index === count - 1;
  const elapsed = frame && timestamps && Number.isFinite(timestamps[frame.index]) && Number.isFinite(timestamps[0]) ? timestamps[frame.index] - timestamps[0] : (frame?.index ?? 0) * interval;
  return <section className="grid gap-4" aria-label="Phát lại capture đồng bộ">
    <div className="flex flex-wrap items-center gap-3 border-y border-[var(--line)] py-3">
      <Button disabled={!frame || !!error} onClick={() => { if (end) { setIndex(0); setPlaying(true); } else setPlaying(v => !v); }}>{end ? "Phát lại" : playing ? "Tạm dừng" : "Phát"}</Button>
      <Button variant="secondary" disabled={!index} onClick={() => {setPlaying(false);setIndex(index-1);}}>← Trước</Button>
      <Button variant="secondary" disabled={end} onClick={() => {setPlaying(false);setIndex(index+1);}}>Sau →</Button>
      <label className="text-sm">Tốc độ <select className="ml-2 rounded border p-2" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[.5,1,2].map(v => <option key={v} value={v}>{v}×</option>)}</select></label>
      <span role="status" className="ml-auto text-xs tabular-nums text-[var(--muted)]">{frame ? `${frame.index+1}/${count} · ${elapsed.toFixed(1)} s` : "Chuẩn bị frame đầu"}{frame && frame.index !== index ? " · Đồng bộ frame tiếp" : ""}</span>
      <input aria-label="Chọn frame phát lại" type="range" min={0} max={count-1} value={index} className="w-full" onChange={e => {setPlaying(false);setIndex(Number(e.target.value));}} />
    </div>
    {error && <div role="alert" className="text-sm text-red-700">{error} · Giữ frame trước.<Button variant="secondary" onClick={() => setRetry(v=>v+1)}>Thử lại</Button></div>}
    <div className="grid gap-4 lg:grid-cols-2">
      <figure className="grid content-start gap-2"><div className="relative overflow-hidden rounded-lg bg-[var(--navy)]">
        <canvas ref={canvas} width={200} height={200} className="aspect-square w-full [image-rendering:pixelated]" aria-label="Occupancy: trước lên trên, trái sang trái; dấu cộng là gốc ego" />
        <span className="absolute left-3 top-3 text-xs text-white">PHÍA TRƯỚC ↑</span><span className="absolute bottom-3 left-3 text-xs text-white">← TRÁI</span><span className="absolute bottom-3 right-3 text-xs text-white">PHẢI →</span>
      </div><figcaption className="text-xs text-[var(--muted)]">100 × 100 m · 0,5 m/ô · + gốc ego · vòng 10/25 m · xanh: tĩnh · cam: vật thể</figcaption></figure>
      {camera && <figure className="grid content-start gap-2"><div className="aspect-video overflow-hidden rounded-lg bg-[var(--navy)]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {frame?.image && <img src={frame.image} className="h-full w-full object-contain" alt={`Camera cùng frame ${frame.index+1} với occupancy`} />}
      </div><figcaption className="text-xs text-[var(--muted)]">Camera phía trước · Cùng frame BEV. Ô cam chưa xác định danh tính từng vật thể.</figcaption></figure>}
    </div>
  </section>;
}
