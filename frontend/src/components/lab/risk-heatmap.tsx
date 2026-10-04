"use client";

import { useState } from "react";
import { Select } from "@/components/ui/select";
import { useNearViewport } from "@/lib/use-near-viewport";

export function RiskHeatmap({ sampleToken, onFrameReady, onFrameError }: { sampleToken: string; onFrameReady?: (token: string) => void; onFrameError?: () => void }) {
  const [system, setSystem] = useState("classical");
  const [vmax, setVmax] = useState(0.3);
  const [failedSrc, setFailedSrc] = useState("");
  const { ref, near } = useNearViewport<HTMLElement>("100px");
  const src = `/api/v1/lab/frames/${encodeURIComponent(sampleToken)}/risk?system=${system}&vmax=${vmax}`;
  const failed = failedSrc === src;

  return <section ref={ref} className="overflow-hidden border-t border-[var(--line)] pt-7">
    <div className="flex flex-col gap-5 pb-4 md:flex-row md:items-end md:justify-between">
      <div><p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[var(--accent-strong)]">03 / Ước lượng rủi ro</p><h2 className="mt-1 text-lg font-semibold tracking-[-0.025em]">Risk heatmap</h2><p className="mt-1 text-xs text-[var(--muted)]">Điểm rủi ro chưa hiệu chuẩn; không phải xác suất va chạm.</p></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Nguồn risk" value={system} onChange={(event) => setSystem(event.target.value)}><option value="classical">Classical LiDAR</option><option value="oracle">Oracle · GT reference</option></Select>
        <Select label="Thang màu tối đa" value={vmax} onChange={(event) => setVmax(Number(event.target.value))}>{[0.2,0.3,0.4,0.5,0.6].map((value) => <option key={value} value={value}>{value.toFixed(1)}</option>)}</Select>
      </div>
    </div>
    <div className="grid min-h-[420px] place-items-center rounded-[var(--radius)] bg-[#0b171c] p-4">
      {!near ? <p className="text-sm text-slate-400">Heatmap sẽ tải khi bạn cuộn tới khu vực này.</p> : failed ? <div className="max-w-md text-center text-sm leading-6 text-amber-300">Heatmap chưa sẵn sàng. Kiểm tra `stage_h/risk_out.mat` và dependency SciPy trên backend.</div> :
        /* eslint-disable-next-line @next/next/no-img-element */
        <img alt={`Risk heatmap ${system}`} className="aspect-square w-full max-w-[620px] object-contain" key={src} onLoad={() => onFrameReady?.(sampleToken)} onError={() => { setFailedSrc(src); onFrameError?.(); }} src={src} />}
    </div>
  </section>;
}
