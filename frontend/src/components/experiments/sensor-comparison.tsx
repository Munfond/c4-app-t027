"use client";

import { useEffect, useRef, useState } from "react";
import { apiJson } from "@/lib/lab-api";

type Cloud = { count: number; displayed: number; points: number[][]; speed?: number[] };
type PointSettings = { keep_fraction: number; range_m: number; horizontal_fov: number; noise_std_m: number };
type Preview = { frame_id: string; profile: { name: string; lidar: PointSettings; radar: PointSettings; camera: object };
  sensors: { lidar: Cloud; radar: Cloud }; camera: { channel: string; width: number; height: number; encoded_bytes: number; psnr_db: number }[] };
type Prediction = { frame_id: string; checkpoint_sha256: string; cells: number[] };

function PointPlot({ cloud, radar, label, displayLimit = cloud.displayed }: { cloud: Cloud; radar: boolean; label: string; displayLimit?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const displayed = Math.min(cloud.displayed, displayLimit);
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#10262e"; ctx.fillRect(0, 0, 400, 400);
    ctx.strokeStyle = "#36505a";
    for (let i = 0; i <= 400; i += 80) { ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 400); ctx.moveTo(0, i); ctx.lineTo(400, i); ctx.stroke(); }
    for (let position = 0; position < displayed; position++) {
      const i = Math.floor(position * cloud.points.length / displayed);
      const [forward, left] = cloud.points[i];
      if (Math.abs(forward) > 100 || Math.abs(left) > 100) continue;
      ctx.fillStyle = radar ? (cloud.speed?.[i] ?? 0) > 2 ? "#ffb14c" : "#82d5ce" : "#82d5ce";
      ctx.fillRect(200 - left * 2, 200 - forward * 2, radar ? 4 : 1.5, radar ? 4 : 1.5);
    }
    ctx.fillStyle = "white"; ctx.fillRect(197, 195, 6, 10);
  }, [cloud, radar, displayed]);
  return <figure className="grid gap-2"><figcaption className="text-xs font-semibold">{label} · {cloud.count.toLocaleString("vi-VN")} điểm</figcaption>
    <canvas ref={canvas} width={400} height={400} aria-label={label} className="aspect-square w-full rounded-lg" />
    <p className="text-xs text-[var(--muted)]">Vẽ {displayed.toLocaleString("vi-VN")} điểm · miền ±100 m · phía trước ↑, trái ←{radar ? " · cam: tốc độ >2 m/s" : ""}</p></figure>;
}

function GridPlot({ cells, label, difference = false }: { cells: number[]; label: string; difference?: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || cells.length !== 40000) return;
    const pixels = ctx.createImageData(200, 200);
    const colors = difference ? [[16, 38, 46], [228, 93, 157]] : [[16, 38, 46], [80, 167, 152], [255, 177, 76]];
    cells.forEach((value, i) => pixels.data.set([...colors[value], 255], ((199 - Math.floor(i / 200)) * 200 + 199 - i % 200) * 4));
    ctx.putImageData(pixels, 0, 0);
  }, [cells, difference]);
  return <figure className="grid gap-2"><figcaption className="text-xs font-semibold">{label}</figcaption><canvas ref={canvas} width={200} height={200} aria-label={label} className="aspect-square w-full rounded-lg bg-[var(--navy)] [image-rendering:pixelated]" /></figure>;
}

export function SensorComparison({ baseline, candidate, model, frame, session, channel }: {
  baseline: string; candidate: string; model: string; frame: number; session: string; channel: string;
}) {
  const key = `${baseline}:${candidate}:${model}:${frame}:${session}`;
  const [result, setResult] = useState<{ key: string; data?: [Preview, Preview, Prediction, Prediction]; error?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const url = (job: string, path: string) => `/api/v1/experiments/${job}/${path}${path.includes("?") ? "&" : "?"}session=${session}`;
    void Promise.all([apiJson<Preview>(url(baseline, `sensor-preview?index=${frame}`), controller.signal),
      apiJson<Preview>(url(candidate, `sensor-preview?index=${frame}`), controller.signal),
      apiJson<Prediction>(url(baseline, `predictions/${model}/${frame}`), controller.signal),
      apiJson<Prediction>(url(candidate, `predictions/${model}/${frame}`), controller.signal)])
      .then(data => {
        if (controller.signal.aborted) return;
        if (new Set(data.map(d => d.frame_id)).size !== 1 || data[2].checkpoint_sha256 !== data[3].checkpoint_sha256)
          throw new Error("Không thể đối chiếu: frame hoặc checkpoint khác nhau.");
        setResult({ key, data });
      }).catch(error => { if (!controller.signal.aborted) setResult({ key, error: String(error) }); });
    return () => controller.abort();
  }, [baseline, candidate, model, frame, session, key]);
  if (result?.key !== key) return <p role="status" className="text-sm">Đang tải dữ liệu đối chiếu…</p>;
  if (!result.data) return <p role="alert" className="text-sm text-red-700">{result.error}</p>;
  const [before, after, basePrediction, prediction] = result.data;
  const differences = prediction.cells.map((cell, i) => Number(cell !== basePrediction.cells[i]));
  const changed = differences.reduce((a, b) => a + b, 0);
  const beforeCamera = before.camera.find(c => c.channel === channel), afterCamera = after.camera.find(c => c.channel === channel);
  return <section className="grid gap-5 border-t pt-4">
    <h3 className="font-semibold">Dữ liệu và dự đoán trước / sau</h3>
    <p className="text-xs text-[var(--muted)]">Cùng frame {before.frame_id.slice(0, 8)} · cùng model {model}. Đám mây điểm lấy mẫu theo tỷ lệ giảm để hiển thị mật độ tương đối; số lượng là số điểm thực trước khi tạo đặc trưng.</p>
    {(["lidar", "radar"] as const).map(sensor => <details key={sensor} open><summary className="cursor-pointer text-sm font-semibold">{sensor === "lidar" ? "LiDAR" : "Radar"} · {before.sensors[sensor].count ? `${((1 - after.sensors[sensor].count / before.sensors[sensor].count) * 100).toFixed(1)}% điểm giảm` : "Nguồn không có điểm"}</summary>
      <div className="mt-3 grid gap-4 sm:grid-cols-2"><PointPlot cloud={before.sensors[sensor]} radar={sensor === "radar"} label={`${sensor} baseline`} /><PointPlot cloud={after.sensors[sensor]} radar={sensor === "radar"} label={`${sensor} ${after.profile.name}`} displayLimit={before.sensors[sensor].count ? Math.ceil(before.sensors[sensor].displayed * after.sensors[sensor].count / before.sensors[sensor].count) : after.sensors[sensor].displayed} /></div>
      <p className="mt-2 text-xs">Thông số {after.profile.name}: giữ {(after.profile[sensor].keep_fraction * 100).toFixed(0)}% điểm sau lọc · khoảng cách {after.profile[sensor].range_m} m · góc ngang {after.profile[sensor].horizontal_fov}° · nhiễu tọa độ {after.profile[sensor].noise_std_m} m.</p>
    </details>)}
    <details open><summary className="cursor-pointer text-sm font-semibold">Occupancy · {(changed / 40000 * 100).toFixed(2)}% ô khác baseline</summary>
      <div className="mt-3 grid gap-3 sm:grid-cols-3"><GridPlot cells={basePrediction.cells} label="Occupancy baseline" /><GridPlot cells={prediction.cells} label={`Occupancy ${after.profile.name}`} /><GridPlot cells={differences} label="Ô thay đổi (hồng)" difference /></div>
      <p className="mt-2 text-xs text-[var(--muted)]">Miền ±50 m · static xanh, object cam. Ô khác nhau không đồng nghĩa ô sai; xem IoU để đánh giá chất lượng.</p>
    </details>
    {beforeCamera && afterCamera ? <p className="rounded-lg bg-[var(--surface-subtle)] p-3 text-xs">Camera {channel}: {beforeCamera.width}×{beforeCamera.height} → {afterCamera.width}×{afterCamera.height} · {(beforeCamera.encoded_bytes / 1000).toFixed(1)} → {(afterCamera.encoded_bytes / 1000).toFixed(1)} kB · PSNR {afterCamera.psnr_db.toFixed(1)} dB. Hai ảnh dưới đây được hiển thị cùng kích thước khung.</p> : null}
    {baseline === candidate ? <p className="text-xs text-amber-800">Đang xem baseline: dữ liệu và dự đoán hai bên giống nhau. Chọn ứng viên ở “Cấu hình xem trước” để xem thay đổi.</p> : null}
  </section>;
}
