"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/lab-api";
export type RuntimeStatus = { hardware_ready: boolean | null; managed: boolean; notice: string;
  memory_available_gib?: number | null; memory_required_gib?: number };

export function CarlaRuntimeNotice({ active, onStatus, compact = false }: { active: boolean; compact?: boolean; onStatus: (status: RuntimeStatus | null) => void }) {
  const [data, setData] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      try {
        const result = await apiJson<RuntimeStatus>("/api/v1/experiments/runtime", controller.signal);
        if (!controller.signal.aborted) { setData(result); onStatus(result); setError(""); }
      } catch {
        if (!controller.signal.aborted) { setError("Chưa kiểm tra được runtime. Bản ghi hoàn tất vẫn xem được; job mới cần worker và CARLA chạy."); onStatus(null); }
      }
      if (!controller.signal.aborted) timer = setTimeout(check, 15000);
    }
    void check();
    return () => {controller.abort();clearTimeout(timer);};
  }, [active, onStatus]);
  if (!data && !error) return <p role="status" className="text-xs text-[var(--muted)]">Đang kiểm tra điều kiện capture…</p>;
  return <div className="border-l-2 border-[var(--accent)] pl-3 text-sm" role="status">
    <p>{error || data?.notice}</p>
    {data?.managed && !compact && <p className="mt-1 text-xs text-[var(--muted)]">RAM khả dụng: {data.memory_available_gib ?? "chưa đọc được"} GiB · ngưỡng bắt đầu: {data.memory_required_gib} GiB. Xem preview không cần khởi động simulator.</p>}
  </div>;
}
