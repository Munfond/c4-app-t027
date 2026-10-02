"use client";

import { useState } from "react";
import { Select } from "@/components/ui/select";

export function RiskHeatmap({ sampleToken }: { sampleToken: string }) {
  const [system, setSystem] = useState("classical");
  const [vmax, setVmax] = useState(0.3);
  const [failed, setFailed] = useState(false);
  const src = `/api/v1/lab/frames/${encodeURIComponent(sampleToken)}/risk?system=${system}&vmax=${vmax}`;

  return <section className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-white shadow-[var(--shadow)]">
    <div className="flex flex-col gap-4 border-b border-[var(--line)] p-4 md:flex-row md:items-end md:justify-between">
      <div><p className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--accent-strong)]">Stage H · Precomputed</p><h2 className="mt-1 text-base font-bold">Risk heatmap</h2><p className="mt-1 text-xs text-[var(--muted)]">Điểm risk chưa hiệu chuẩn, không phải xác suất va chạm.</p></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Nguồn risk" value={system} onChange={(event) => { setFailed(false); setSystem(event.target.value); }}><option value="classical">Classical LiDAR</option><option value="oracle">Oracle · GT reference</option></Select>
        <Select label="Thang màu tối đa" value={vmax} onChange={(event) => { setFailed(false); setVmax(Number(event.target.value)); }}>{[0.2,0.3,0.4,0.5,0.6].map((value) => <option key={value} value={value}>{value.toFixed(1)}</option>)}</Select>
      </div>
    </div>
    <div className="grid min-h-[420px] place-items-center bg-[#0b1114] p-4">
      {failed ? <div className="max-w-md text-center text-sm leading-6 text-amber-300">Heatmap chưa sẵn sàng. Kiểm tra `stage_h/risk_out.mat` và dependency SciPy trên backend.</div> :
        /* eslint-disable-next-line @next/next/no-img-element */
        <img alt={`Risk heatmap ${system}`} className="aspect-square w-full max-w-[620px] rounded-xl object-contain" key={src} onError={() => setFailed(true)} src={src} />}
    </div>
  </section>;
}
