"use client";

import { useEffect, useState } from "react";

export interface CameraCardProps {
  sampleToken: string;
  channel: string;
  label: string;
  isFocused?: boolean;
  onFocus?: () => void;
  onFrameSettled?: (token: string, channel: string) => void;
}

export function CameraCard({ sampleToken, channel, label, isFocused = false, onFocus, onFrameSettled }: CameraCardProps) {
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<{key: string; url?: string; error?: number} | null>(null);
  const key = `${sampleToken}:${channel}:${retry}`;
  const current = result?.key === key ? result : null;
  useEffect(() => { if (current?.url || current?.error) onFrameSettled?.(sampleToken, channel); }, [current, sampleToken, channel, onFrameSettled]);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    if (!sampleToken) return;
    void fetch(`/api/v1/lab/frames/${encodeURIComponent(sampleToken)}/cameras/${channel}?retry=${retry}`, {signal: controller.signal})
      .then(async response => {
        if (!response.ok) {
          if (!controller.signal.aborted) setResult({key, error: response.status});
          return;
        }
        if (response.headers.get("x-anonymized") !== "true") throw new Error("Unprocessed image");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setResult({key, url: objectUrl});
      }).catch(() => { if (!controller.signal.aborted) setResult({key, error: 503}); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [sampleToken, channel, retry, key]);

  const heading = <><span className="font-semibold text-[var(--foreground)]">{label}</span><span className={current?.error ? "text-amber-800" : "text-[var(--accent-strong)]"}>{current?.url ? "Đã qua bộ lọc" : current?.error ? "Chưa sẵn sàng" : "Đang tải…"}</span></>;
  return <article className={`overflow-hidden rounded-lg border bg-white ${isFocused && onFocus ? "border-[var(--accent)]" : "border-[var(--line)]"}`}>
    {onFocus ? <button type="button" onClick={onFocus} aria-label={`Xem camera ${label}`} className="flex min-h-11 w-full items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2 text-left text-xs hover:bg-[var(--surface-subtle)]">{heading}</button> : <div className="flex min-h-11 items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2 text-xs">{heading}</div>}
    <div className="relative flex aspect-video items-center justify-center bg-[#0b2028] text-slate-300">
      {current?.url ? <>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={current.url} alt={`${label} · ảnh đã qua bộ lọc khuôn mặt và biển số`} className="h-full w-full object-contain" onError={() => setResult({key, error: 503})} />
      </> : current?.error ? <div role="status" className="max-w-72 p-4 text-center text-xs">
        <p className="font-semibold text-amber-200">Chưa có ảnh đã xử lý</p>
        <p className="my-2 text-slate-300">Camera của frame này chưa sẵn sàng. Chọn frame khác hoặc thử lại sau.</p>
        <button type="button" onClick={() => setRetry(value => value + 1)} className="rounded-md border border-slate-500 px-3 py-1.5 text-white hover:bg-white/10">Thử lại</button>
      </div> : <div role="status" className="flex items-center gap-2 text-xs"><span className="h-4 w-4 animate-spin rounded-full border-2 border-teal-300 border-t-transparent" />Đang tải camera…</div>}
    </div>
  </article>;
}
