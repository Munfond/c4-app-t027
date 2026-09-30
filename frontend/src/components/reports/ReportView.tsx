"use client";

import React, { useState, useEffect } from "react";
import {
  DetectionBenchmarkTable,
  OccupancyBenchmarkTable,
  FlowBenchmarkTable,
  RiskBenchmarkTable,
  DetectionRow,
  OccupancyItem,
  FlowItem,
  RiskItem,
} from "../benchmark/BenchmarkTables";

export interface BenchmarkReportData {
  split: string;
  frame_count: number;
  sections: {
    detection?: { available: boolean; source: string; data: { rows?: DetectionRow[] } | null };
    occupancy?: {
      available: boolean;
      source: string;
      data: { binary_occupancy?: OccupancyItem[] } | null;
    };
    flow?: {
      available: boolean;
      source: string;
      data: {
        learned?: Record<string, { EPE_moving_all: number; angle_median_deg: number; mIoU?: number; IoU_occupied?: number }>;
      } | null;
    };
    risk?: {
      available: boolean;
      source: string;
      data: {
        systems?: Record<
          string,
          {
            "MAE_vs_oracle[all objects]": number;
            Spearman_vs_oracle: number;
            high_risk_precision: number;
            high_risk_recall: number;
            "min_TTC_MAE_s(where both finite)": number;
          }
        >;
      } | null;
    };
  };
  limitations: string[];
}

export function ReportView({ className = "" }: { className?: string }) {
  const [report, setReport] = useState<BenchmarkReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"all" | "detection" | "occupancy" | "flow" | "risk">("all");

  const fetchReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/lab/benchmarks");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: Không thể tải báo cáo số liệu`);
      }
      const data: BenchmarkReportData = await res.json();
      setReport(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đã có lỗi xảy ra");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, []);

  // Format flow items
  const flowItems: FlowItem[] = React.useMemo(() => {
    if (!report?.sections?.flow?.data?.learned) return [];
    return Object.entries(report.sections.flow.data.learned).map(([name, item]) => ({
      name,
      EPE: item.EPE_moving_all,
      angle_deg: item.angle_median_deg,
      mIoU: item.mIoU,
      IoU_occupied: item.IoU_occupied,
    }));
  }, [report]);

  // Format risk items
  const riskItems: RiskItem[] = React.useMemo(() => {
    if (!report?.sections?.risk?.data?.systems) return [];
    return Object.entries(report.sections.risk.data.systems).map(([name, item]) => ({
      name,
      mae: item["MAE_vs_oracle[all objects]"],
      spearman: item.Spearman_vs_oracle,
      high_risk_precision: item.high_risk_precision,
      high_risk_recall: item.high_risk_recall,
      ttc_mae: item["min_TTC_MAE_s(where both finite)"],
    }));
  }, [report]);

  if (loading) {
    return (
      <div className="flex flex-col gap-4 p-6 rounded-2xl border border-zinc-800 bg-zinc-950">
        <div className="flex items-center gap-3">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          <span className="text-sm text-zinc-400">Đang nạp bảng chỉ số Benchmark và Provenance...</span>
        </div>
        <div className="space-y-3">
          <div className="h-20 w-full animate-pulse rounded-xl bg-zinc-900" />
          <div className="h-40 w-full animate-pulse rounded-xl bg-zinc-900" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 rounded-2xl border border-zinc-800 bg-zinc-950 text-center">
        <svg className="h-10 w-10 text-rose-400 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <div className="text-sm font-semibold text-zinc-200 mb-1">{error}</div>
        <p className="text-xs text-zinc-400 max-w-md mb-4">
          Không thể kết nối tới API `/api/v1/lab/benchmarks`. Vui lòng kiểm tra lại dịch vụ Backend.
        </p>
        <button
          onClick={fetchReport}
          className="rounded-lg bg-zinc-800 hover:bg-zinc-700 px-3.5 py-1.5 text-xs font-medium text-white transition-colors border border-zinc-700"
        >
          Tải lại dữ liệu
        </button>
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-6 text-zinc-100 ${className}`}>
      {/* Overview Banner */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-6 flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="rounded bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-400 border border-blue-500/20">
                Evaluation Split: {report?.split || "mini_val"}
              </span>
              <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs font-mono text-zinc-300">
                {report?.frame_count || 81} Frames (2 Scenes)
              </span>
            </div>
            <h1 className="text-lg font-bold text-white tracking-tight">
              Báo cáo Thực nghiệm & Đánh giá Đa mô hình ADAS
            </h1>
            <p className="text-xs text-zinc-400 mt-0.5">
              So sánh hiệu năng giữa các cụm cảm biến Camera, LiDAR, Radar và mô hình lưới chiếm dụng không gian.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchReport}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Làm mới số liệu
            </button>
          </div>
        </div>

        {/* Limitations & Provenance Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Limitations Box */}
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-amber-400 mb-2">
              <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>Giới hạn Khoa học & Cảnh báo Bắt buộc</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px] text-zinc-400">
              {report?.limitations.map((lim, idx) => (
                <li key={idx} className="leading-relaxed">
                  {lim}
                </li>
              ))}
            </ul>
          </div>

          {/* Provenance Box */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-zinc-300 mb-2">
              <svg className="h-4 w-4 text-blue-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Nguồn Dữ liệu Xác thực (Artifact Provenance)</span>
            </div>
            <div className="space-y-1.5 text-[11px]">
              {report?.sections &&
                Object.entries(report.sections).map(([key, sec]) => (
                  <div key={key} className="flex items-center justify-between text-zinc-400">
                    <span className="capitalize font-medium text-zinc-300">{key}:</span>
                    <span className="font-mono text-[10px] text-zinc-500 truncate max-w-[240px]" title={sec?.source}>
                      {sec?.source}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs Selector */}
      <div className="flex flex-wrap gap-2 border-b border-zinc-800 pb-3">
        {[
          { id: "all", label: "Tất cả bảng chỉ số" },
          { id: "detection", label: "1. Nhận diện 3D (Detection)" },
          { id: "occupancy", label: "2. Lưới chiếm dụng (Occupancy)" },
          { id: "flow", label: "3. Dòng chảy 4D (Flow)" },
          { id: "risk", label: "4. Đánh giá rủi ro (Risk)" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
              activeTab === tab.id
                ? "bg-blue-600 text-white shadow-md shadow-blue-500/20"
                : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 border border-zinc-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tables Content */}
      <div className="flex flex-col gap-6">
        {(activeTab === "all" || activeTab === "detection") && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">1. Nhận diện Hộp bao 3D (3D Bounding Box Detection)</h2>
              <span className="text-[11px] text-zinc-500">Tiêu chuẩn đánh giá nuScenes Detection</span>
            </div>
            <DetectionBenchmarkTable rows={report?.sections?.detection?.data?.rows || []} />
          </div>
        )}

        {(activeTab === "all" || activeTab === "occupancy") && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">2. Lưới chiếm dụng không gian (3D Occupancy Grid)</h2>
              <span className="text-[11px] text-zinc-500">Độ phân giải 200x200 ô (0.5m/ô)</span>
            </div>
            <OccupancyBenchmarkTable items={report?.sections?.occupancy?.data?.binary_occupancy || []} />
          </div>
        )}

        {(activeTab === "all" || activeTab === "flow") && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">3. Dòng chảy chuyển động thời gian (Temporal Occupancy Flow)</h2>
              <span className="text-[11px] text-zinc-500">Sai số điểm cuối EPE (m/s)</span>
            </div>
            <FlowBenchmarkTable items={flowItems} />
          </div>
        )}

        {(activeTab === "all" || activeTab === "risk") && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">4. Đánh giá Trường Rủi ro Va chạm (Risk Assessment)</h2>
              <span className="text-[11px] text-zinc-500">Đối chiếu với điểm chuẩn Oracle</span>
            </div>
            <RiskBenchmarkTable items={riskItems} />
          </div>
        )}
      </div>
    </div>
  );
}
