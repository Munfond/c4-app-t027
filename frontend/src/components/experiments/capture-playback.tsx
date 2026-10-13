"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { apiJson } from "@/lib/lab-api";

type Actor = {id:number; x:number; y:number; l:number; w:number; h:number; yaw:number; camera_box_uv?: [number,number,number,number] | null; camera_projection_status?: string};
type Reference = { cells: number[]; valid: boolean[]; actors?: Actor[] };
type Frame = { index: number; cells: number[]; image: string | null; reference: Reference | null };
export function CapturePlayback({ job, model, count, interval, camera, active, timestamps, apiBase, frameNotes }: {
  job: string; model: string; count: number; interval: number; camera: boolean; active: boolean; timestamps?: number[]; apiBase?: string; frameNotes?: string[];
}) {
  const base = apiBase ?? `/api/v1/experiments/${job}`;
  const [index, setIndex] = useState(0);
  const [referenceMode, setReferenceMode] = useState(false);
  const [selectedActorId, setSelectedActorId] = useState<number | null>(null);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [skipGaps, setSkipGaps] = useState(true);
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
        const [data, blob, reference] = await Promise.all([
          apiJson<{ cells: number[] }>(`${base}/predictions/${encodeURIComponent(model)}/${target}`),
          camera ? fetch(`${base}/camera?index=${target}`).then(async r => {
            if (!r.ok) throw new Error(`Camera HTTP ${r.status}`);
            return r.blob();
          }) : Promise.resolve(null),
          camera ? apiJson<Reference>(`${base}/reference/${target}`).catch(() => null) : Promise.resolve(null),
        ]);
        if (data.cells.length !== 40000 || data.cells.some(value => !Number.isInteger(value) || value < 0 || value > 2)) throw new Error("Lưới occupancy không hợp lệ");
        const image = blob ? URL.createObjectURL(blob) : null;
        if (image) {
          try { const img = new window.Image(); img.src = image; await img.decode(); }
          catch (cause) { URL.revokeObjectURL(image); throw cause; }
        }
        if (!alive.current) { if (image) URL.revokeObjectURL(image); throw new Error("Preview closed"); }
        const ready = { index: target, cells: data.cells, image, reference: reference?.cells.length === 40000 && reference.valid.length === 40000 ? reference : null };
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
  }, [job, model, index, count, camera, retry, base]);
  const measuredGap = timestamps && timestamps[index + 1] - timestamps[index];
  const nextGap = measuredGap && Number.isFinite(measuredGap) && measuredGap > 0 ? measuredGap : interval;
  const playbackGap = skipGaps ? Math.min(nextGap, interval) : nextGap;
  useEffect(() => {
    if (!playing || !active || error || frame?.index !== index || (index === count - 1 && !loop) || count < 2) return;
    const timer = setTimeout(() => setIndex(index === count - 1 ? 0 : index + 1), Math.max(80, playbackGap * 1000 / speed));
    return () => clearTimeout(timer);
  }, [playing, active, error, frame, index, count, playbackGap, speed, loop]);
  const isReference = referenceMode && !!frame?.reference;
  const visibleActors = [...(frame?.reference?.actors ?? [])].filter(actor => Math.abs(actor.x) <= 50 && Math.abs(actor.y) <= 50).sort((a,b) => Math.hypot(a.x,a.y) - Math.hypot(b.x,b.y)).slice(0,6);
  const selectedActor = visibleActors.find(actor => actor.id === selectedActorId);
  useLayoutEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || !frame) return;
    const pixels = ctx.createImageData(200, 200);
    const colors = [[16, 38, 46], [80, 167, 152], [255, 177, 76]];
    const display = isReference ? frame.reference!.cells : frame.cells;
    display.forEach((v, cell) => pixels.data.set([...(isReference && !frame.reference!.valid[cell] ? [45, 53, 57] : colors[v] ?? colors[0]), 255], ((199 - Math.floor(cell / 200)) * 200 + 199 - cell % 200) * 4));
    ctx.putImageData(pixels, 0, 0);
    ctx.strokeStyle = "rgba(255,255,255,.2)"; ctx.lineWidth = .4;
    for (const radius of [20, 50]) {
      ctx.beginPath(); ctx.arc(100,100,radius,0,Math.PI*2);ctx.stroke();
    }
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = .8;
    ctx.beginPath(); ctx.moveTo(96,100);ctx.lineTo(104,100);ctx.moveTo(100,96);ctx.lineTo(100,104);ctx.stroke();
    if (isReference && selectedActor) {
      const actor = selectedActor;
      ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1;
      ctx.beginPath();
      [[-1,-1],[1,-1],[1,1],[-1,1]].forEach(([a,b],i) => {
        const dx=a*actor.l/2, dy=b*actor.w/2;
        const x=actor.x+Math.cos(actor.yaw)*dx-Math.sin(actor.yaw)*dy;
        const y=actor.y+Math.sin(actor.yaw)*dx+Math.cos(actor.yaw)*dy;
        if (!i) ctx.moveTo(100-2*y,100-2*x); else ctx.lineTo(100-2*y,100-2*x);
      });
      ctx.closePath();ctx.stroke();
    }
  }, [frame, isReference, selectedActor]);
  const end = index === count - 1;
  const hasGaps = timestamps?.some((time,i) => i > 0 && Number.isFinite(time) && Number.isFinite(timestamps[i-1]) && time - timestamps[i-1] > interval + 0.01);
  const elapsed = frame && timestamps && Number.isFinite(timestamps[frame.index]) && Number.isFinite(timestamps[0]) ? timestamps[frame.index] - timestamps[0] : (frame?.index ?? 0) * interval;
  return <section className="grid gap-4" aria-label="Phát lại capture đồng bộ">
    <div className="flex flex-wrap items-center gap-3 border-y border-[var(--line)] py-3">
      <Button disabled={!frame || !!error || count < 2} onClick={() => { if (playing && (!end || loop)) setPlaying(false); else { if(end)setIndex(0);setPlaying(true); } }}>{count < 2 ? "Một frame" : playing && (!end || loop) ? "Tạm dừng" : end ? "Phát lại" : "Phát"}</Button>
      <Button variant="secondary" disabled={!index} onClick={() => {setPlaying(false);setIndex(index-1);}}>← Trước</Button>
      <Button variant="secondary" disabled={end} onClick={() => {setPlaying(false);setIndex(index+1);}}>Sau →</Button>
      <label className="text-sm">Tốc độ <select className="ml-2 rounded border p-2" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[.5,1,2].map(v => <option key={v} value={v}>{v}×</option>)}</select></label>
      <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={loop} disabled={count < 2} onChange={e => setLoop(e.target.checked)} />Lặp capture</label>
      {hasGaps && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={skipGaps} onChange={e => setSkipGaps(e.target.checked)} />Rút ngắn khoảng trống</label>}
      <span role="status" className="ml-auto text-xs tabular-nums text-[var(--muted)]">{frame ? `${frame.index+1}/${count} · ${elapsed.toFixed(1)} s` : "Chuẩn bị frame đầu"}{frame && frame.index !== index ? " · Đồng bộ frame tiếp" : ""}</span>
      <input aria-label="Chọn frame phát lại" type="range" min={0} max={count-1} value={index} className="w-full" onChange={e => {setPlaying(false);setIndex(Number(e.target.value));}} />
    </div>
    {frame && frameNotes?.[frame.index] && <p className="border-l-2 border-[var(--accent)] pl-3 text-sm tabular-nums">{frameNotes[frame.index]}</p>}
    <p className="text-xs text-[var(--muted)]">Phát lại dữ liệu đã ghi, thời gian từ capture gốc.{loop ? " Lặp sẽ trở về frame đầu, không phải mô phỏng trực tiếp." : ""}{hasGaps ? " Rút ngắn khoảng trống chỉ đổi tốc độ xem, không tạo thêm frame." : ""}</p>
    {error && <div role="alert" className="text-sm text-red-700">{error} · Giữ frame trước.<Button variant="secondary" onClick={() => setRetry(v=>v+1)}>Thử lại</Button></div>}
    <div className="flex flex-wrap items-center gap-2" aria-label="Đối chiếu output với reference">
      <Button variant="secondary" aria-pressed={!isReference} onClick={() => setReferenceMode(false)}>Model</Button>
      <Button variant="secondary" aria-pressed={isReference} disabled={!frame?.reference} onClick={() => setReferenceMode(true)}>Reference</Button>
      <span className="text-xs text-[var(--muted)]">{isReference ? "Xám: ô chưa được reference quan sát. Tĩnh là proxy theo độ cao, vật thể từ footprint actor." : frame?.reference ? "Chuyển Reference để xem vùng/vật thể model bỏ sót." : "Reference chưa sẵn sàng cho capture này."}</span>
    </div>
    {isReference && visibleActors.length > 0 && <div className="grid gap-2">
      <div className="flex flex-wrap gap-2" aria-label="Chọn footprint actor tham chiếu gần ego">{visibleActors.map(actor => <Button key={actor.id} variant="secondary" aria-pressed={selectedActorId === actor.id} onClick={() => {setSelectedActorId(actor.id);setPlaying(false);}}>
        #{actor.id} · {Math.hypot(actor.x,actor.y).toFixed(1)} m
      </Button>)}</div>
      <p className="text-xs text-[var(--muted)]">{selectedActor ? `#${selectedActor.id}: ${Math.abs(selectedActor.x).toFixed(1)} m ${selectedActor.x >= 0 ? "phía trước" : "phía sau"}, ${Math.abs(selectedActor.y).toFixed(1)} m bên ${selectedActor.y >= 0 ? "trái" : "phải"}; dài × rộng × cao ${selectedActor.l.toFixed(1)} × ${selectedActor.w.toFixed(1)} × ${selectedActor.h.toFixed(1)} m. Viền trắng là footprint reference.` : "Chọn actor để xem vị trí và kích thước, không cần tên lớp."} Đây là metadata CARLA, không phải detection của model hoặc phép ghép danh tính trên ảnh camera.</p>
    </div>}
    <div className="grid gap-4 lg:grid-cols-2">
      <figure className="grid content-start gap-2"><div className="relative overflow-hidden rounded-lg bg-[var(--navy)]">
        <canvas ref={canvas} width={200} height={200} className="aspect-square w-full [image-rendering:pixelated]" aria-label="Occupancy: trước lên trên, trái sang trái; dấu cộng là gốc ego" />
        <span className="absolute left-3 top-3 text-xs text-white">PHÍA TRƯỚC ↑</span><span className="absolute bottom-3 left-3 text-xs text-white">← TRÁI</span><span className="absolute bottom-3 right-3 text-xs text-white">PHẢI →</span>
      </div><figcaption className="text-xs text-[var(--muted)]">{isReference ? "REFERENCE" : "MODEL"} · 100 × 100 m · 0,5 m/ô · + gốc ego · vòng 10/25 m · xanh: tĩnh · cam: vật thể</figcaption></figure>
      {camera && <figure className="grid content-start gap-2"><div className="relative aspect-video overflow-hidden rounded-lg bg-[var(--navy)]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {frame?.image && <img src={frame.image} className="h-full w-full object-contain" alt={`Camera cùng frame ${frame.index+1} với occupancy`} />}
        {isReference && selectedActor?.camera_box_uv && <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full" aria-label={`Khung chiếu hình học reference #${selectedActor.id}, không phải detection ảnh`}>
          {([["#10262e",4],["#d9ee98",2]] as const).map(([color,width])=><rect key={color} x={selectedActor.camera_box_uv![0]*100} y={selectedActor.camera_box_uv![1]*100} width={(selectedActor.camera_box_uv![2]-selectedActor.camera_box_uv![0])*100} height={(selectedActor.camera_box_uv![3]-selectedActor.camera_box_uv![1])*100} fill="none" stroke={color} strokeWidth={width} vectorEffect="non-scaling-stroke" />)}
        </svg>}
      </div><figcaption className="text-xs text-[var(--muted)]">Camera phía trước · Cùng frame BEV. {isReference && selectedActor?.camera_box_uv ? `Viền sáng: phép chiếu reference #${selectedActor.id}, chưa xét che khuất/khả năng nhìn thấy; không phải detection ảnh.` : isReference && selectedActor?.camera_projection_status === "geometry_recorded" ? "Actor được chọn không có khung chiếu hợp lệ trên ảnh này (ngoài khung hoặc quá gần camera)." : "Ô cam chưa xác định danh tính từng vật thể; capture cũ có thể thiếu camera calibration."}</figcaption></figure>}
    </div>
  </section>;
}
