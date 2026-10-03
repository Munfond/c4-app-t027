"use client";

import React from "react";

export interface DetectionRow {
  model: string;
  training: string;
  mAP: number;
  NDS: number;
  mATE: number;
  mAVE: number;
  per_class_AP_2m?: Record<string, number>;
}

export interface OccupancyItem {
  system: string;
  IoU_occupied: number;
  precision: number;
  recall: number;
  precision_tol1?: number;
  recall_tol1?: number;
}

export interface FlowItem {
  name: string;
  EPE: number;
  angle_deg: number | null;
  mIoU?: number;
  IoU_occupied?: number;
}

export interface RiskItem {
  name: string;
  mae: number;
  spearman: number;
  high_risk_precision: number;
  high_risk_recall: number;
  ttc_mae: number;
}

export function DetectionBenchmarkTable({ rows }: { rows: DetectionRow[] }) {
  if (!rows || rows.length === 0) {
    return <div className="p-4 text-xs text-[var(--muted)]">Chưa có số liệu 3D Detection.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--surface)]">
      <table className="w-full text-left text-xs">
        <thead className="border-b border-[var(--line)] bg-[var(--surface-subtle)] text-[var(--muted)]">
          <tr>
            <th className="px-4 py-3 font-semibold">Mô hình</th>
            <th className="px-3 py-3 font-semibold">Cảm biến & Huấn luyện</th>
            <th className="px-3 py-3 font-semibold text-right">mAP</th>
            <th className="px-3 py-3 font-semibold text-right">NDS</th>
            <th className="px-3 py-3 font-semibold text-right">mATE (m)</th>
            <th className="px-3 py-3 font-semibold text-right">mAVE (m/s)</th>
            <th className="px-3 py-3 font-semibold text-right">AP Car</th>
            <th className="px-3 py-3 font-semibold text-right">AP Pedestrian</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--line)]">
          {rows.map((row, idx) => {
            const isOurs = row.model.toLowerCase().includes("our");
            return (
              <tr
                key={idx}
                className={`transition-colors hover:bg-[var(--surface-subtle)] ${
                  isOurs ? "bg-[var(--accent-soft)]" : ""
                }`}
              >
                <td className="px-4 py-3 font-medium text-[var(--foreground)]">
                  <div className="flex items-center gap-2">
                    {isOurs ? (
                      <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] text-[var(--accent-strong)] border border-[var(--line)]">
                        Our Model
                      </span>
                    ) : (
                      <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-800 border border-amber-200">
                        Official Ref
                      </span>
                    )}
                    <span>{row.model}</span>
                  </div>
                </td>
                <td className="px-3 py-3 text-[var(--muted)] max-w-[200px] truncate" title={row.training}>
                  {row.training}
                </td>
                <td className="px-3 py-3 text-right font-mono font-semibold text-[var(--accent-strong)]">
                  {(row.mAP * 100).toFixed(1)}%
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                  {(row.NDS * 100).toFixed(1)}%
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--muted)]">
                  {row.mATE.toFixed(3)}
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--muted)]">
                  {row.mAVE.toFixed(3)}
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                  {row.per_class_AP_2m?.car !== undefined
                    ? `${(row.per_class_AP_2m.car * 100).toFixed(1)}%`
                    : "-"}
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                  {row.per_class_AP_2m?.pedestrian !== undefined
                    ? `${(row.per_class_AP_2m.pedestrian * 100).toFixed(1)}%`
                    : "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function OccupancyBenchmarkTable({ items }: { items: OccupancyItem[] }) {
  if (!items || items.length === 0) {
    return <div className="p-4 text-xs text-[var(--muted)]">Chưa có số liệu Occupancy.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--surface)]">
      <table className="w-full text-left text-xs">
        <thead className="border-b border-[var(--line)] bg-[var(--surface-subtle)] text-[var(--muted)]">
          <tr>
            <th className="px-4 py-3 font-semibold">Phương pháp</th>
            <th className="px-3 py-3 font-semibold text-right">IoU Chiếm dụng</th>
            <th className="px-3 py-3 font-semibold text-right">Độ chuẩn xác (Precision)</th>
            <th className="px-3 py-3 font-semibold text-right">Độ thu hồi (Recall)</th>
            <th className="px-3 py-3 font-semibold text-right">Precision (±1 cell)</th>
            <th className="px-3 py-3 font-semibold text-right">Recall (±1 cell)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--line)]">
          {items.map((item, idx) => {
            const isBest = item.system.toLowerCase().includes("our_occupancy.pth");
            return (
              <tr
                key={idx}
                className={`transition-colors hover:bg-[var(--surface-subtle)] ${
                  isBest ? "bg-[var(--accent-soft)] font-medium" : ""
                }`}
              >
                <td className="px-4 py-3 text-[var(--foreground)]">
                  <div className="flex items-center gap-2">
                    {isBest && (
                      <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] text-[var(--accent-strong)] border border-[var(--line)]">
                        Top Performer
                      </span>
                    )}
                    <span>{item.system}</span>
                  </div>
                </td>
                <td className="px-3 py-3 text-right font-mono font-semibold text-[var(--accent-strong)]">
                  {(item.IoU_occupied * 100).toFixed(2)}%
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                  {(item.precision * 100).toFixed(2)}%
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                  {(item.recall * 100).toFixed(2)}%
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--muted)]">
                  {item.precision_tol1 !== undefined
                    ? `${(item.precision_tol1 * 100).toFixed(1)}%`
                    : "-"}
                </td>
                <td className="px-3 py-3 text-right font-mono text-[var(--muted)]">
                  {item.recall_tol1 !== undefined
                    ? `${(item.recall_tol1 * 100).toFixed(1)}%`
                    : "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function FlowBenchmarkTable({ items }: { items: FlowItem[] }) {
  if (!items || items.length === 0) {
    return <div className="p-4 text-xs text-[var(--muted)]">Chưa có số liệu Temporal Flow.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--surface)]">
      <table className="w-full text-left text-xs">
        <thead className="border-b border-[var(--line)] bg-[var(--surface-subtle)] text-[var(--muted)]">
          <tr>
            <th className="px-4 py-3 font-semibold">Cấu hình Flow</th>
            <th className="px-3 py-3 font-semibold text-right">Sai số EPE (m/s) ↓</th>
            <th className="px-3 py-3 font-semibold text-right">Sai số góc di chuyển (Median)</th>
            <th className="px-3 py-3 font-semibold text-right">mIoU</th>
            <th className="px-3 py-3 font-semibold text-right">IoU Occupied</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--line)]">
          {items.map((item, idx) => (
            <tr key={idx} className="transition-colors hover:bg-[var(--surface-subtle)]">
              <td className="px-4 py-3 font-medium text-[var(--foreground)]">{item.name}</td>
              <td className="px-3 py-3 text-right font-mono font-semibold text-[var(--accent-strong)]">
                {item.EPE.toFixed(3)}
              </td>
              <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                {item.angle_deg !== null ? `${item.angle_deg.toFixed(1)}°` : "-"}
              </td>
              <td className="px-3 py-3 text-right font-mono text-[var(--muted)]">
                {item.mIoU !== undefined ? `${(item.mIoU * 100).toFixed(1)}%` : "-"}
              </td>
              <td className="px-3 py-3 text-right font-mono text-[var(--muted)]">
                {item.IoU_occupied !== undefined
                  ? `${(item.IoU_occupied * 100).toFixed(1)}%`
                  : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RiskBenchmarkTable({ items }: { items: RiskItem[] }) {
  if (!items || items.length === 0) {
    return <div className="p-4 text-xs text-[var(--muted)]">Chưa có số liệu Đánh giá Rủi ro.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--surface)]">
      <table className="w-full text-left text-xs">
        <thead className="border-b border-[var(--line)] bg-[var(--surface-subtle)] text-[var(--muted)]">
          <tr>
            <th className="px-4 py-3 font-semibold">Thuật toán</th>
            <th className="px-3 py-3 font-semibold text-right">MAE so với Oracle ↓</th>
            <th className="px-3 py-3 font-semibold text-right">Tương quan Spearman ↑</th>
            <th className="px-3 py-3 font-semibold text-right">Độ chuẩn xác rủi ro cao</th>
            <th className="px-3 py-3 font-semibold text-right">Độ thu hồi rủi ro cao</th>
            <th className="px-3 py-3 font-semibold text-right">Sai số TTC (giây) ↓</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--line)]">
          {items.map((item, idx) => (
            <tr key={idx} className="transition-colors hover:bg-[var(--surface-subtle)]">
              <td className="px-4 py-3 font-medium text-[var(--foreground)]">{item.name}</td>
              <td className="px-3 py-3 text-right font-mono font-semibold text-[var(--accent-strong)]">
                {item.mae.toFixed(4)}
              </td>
              <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                {item.spearman.toFixed(3)}
              </td>
              <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                {(item.high_risk_precision * 100).toFixed(1)}%
              </td>
              <td className="px-3 py-3 text-right font-mono text-[var(--foreground)]">
                {(item.high_risk_recall * 100).toFixed(1)}%
              </td>
              <td className="px-3 py-3 text-right font-mono text-[var(--muted)]">
                {item.ttc_mae.toFixed(3)}s
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
