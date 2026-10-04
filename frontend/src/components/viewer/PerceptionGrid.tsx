"use client";

import { useEffect, useRef } from "react";
import type { PerceptionOutput } from "@/lib/perception-api";

export function PerceptionGrid({ data }: { data: PerceptionOutput }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    const size = 800, scale = size / 100;
    context.fillStyle = "#0b2028"; context.fillRect(0, 0, size, size);
    if (data.task === "occupancy" && data.cells) {
      const buffer = document.createElement("canvas"); buffer.width = buffer.height = 200;
      const ctx = buffer.getContext("2d")!;
      const image = ctx.createImageData(200, 200);
      const colors = [[19, 42, 50], [122, 169, 162], [255, 185, 113]];
      data.cells.forEach((value, i) => {
        const row = Math.floor(i / 200), col = i % 200;
        image.data.set([...colors[value], 255], ((199 - row) * 200 + 199 - col) * 4);
      });
      ctx.putImageData(image, 0, 0); context.imageSmoothingEnabled = false; context.drawImage(buffer, 0, 0, size, size);
    }
    context.strokeStyle = "#ffffff12"; context.lineWidth = 1;
    for (let i = 0; i <= size; i += size / 10) {
      context.beginPath(); context.moveTo(i, 0); context.lineTo(i, size); context.moveTo(0, i); context.lineTo(size, i); context.stroke();
    }
    if (data.task === "flow") for (const [forward, left, vf, vl] of data.vectors ?? []) {
      const x = (50 - left) * scale, y = (50 - forward) * scale;
      // Arrow length shows predicted displacement over one second; speed is in m/s.
      const dx = -vl * scale, dy = -vf * scale, angle = Math.atan2(dy, dx);
      context.strokeStyle = Math.hypot(vf, vl) > 2 ? "#ffbb72" : "#8dc7c4";
      context.beginPath(); context.moveTo(x, y); context.lineTo(x + dx, y + dy);
      context.lineTo(x + dx - 4 * Math.cos(angle - .5), y + dy - 4 * Math.sin(angle - .5));
      context.moveTo(x + dx, y + dy); context.lineTo(x + dx - 4 * Math.cos(angle + .5), y + dy - 4 * Math.sin(angle + .5)); context.stroke();
    }
    context.fillStyle = "#d9ee98"; context.beginPath(); context.moveTo(400, 384); context.lineTo(390, 410); context.lineTo(410, 410); context.closePath(); context.fill();
  }, [data]);
  return <div className="perception-grid">
    <div className="grid-axis">↑ Phía trước +50 m <span>Trái +50 m ← · → Phải −50 m</span></div>
    <div className="grid-plot"><canvas ref={canvas} width={800} height={800} role="img" aria-label={data.task === "occupancy" ? "BEV occupancy 200×200: lớp nền, tĩnh, vật thể; xe ở tâm." : `Flow dự đoán: ${data.vectors?.length ?? 0} vector chuyển động trong hệ tọa độ xe.`} /></div>
    <div className="grid-legend">{data.task === "occupancy" ? <><span><i style={{ background: "#132a32" }} />Free / có thể chưa quan sát</span><span><i style={{ background: "#7aa9a2" }} />Static</span><span><i style={{ background: "#ffb971" }} />Object</span></> : <><span>Mũi tên = dịch chuyển dự đoán trong 1 giây</span><span><i style={{ background: "#8dc7c4" }} />≤ 2 m/s</span><span><i style={{ background: "#ffbb72" }} />&gt; 2 m/s</span></>}</div>
  </div>;
}
