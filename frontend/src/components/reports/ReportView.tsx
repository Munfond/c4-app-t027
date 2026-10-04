"use client";

import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
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

const limitationLabels: Record<string, string> = {
  "Static occupancy uses pseudo-GT": "Occupancy tĩnh được đối chiếu với nhãn pseudo-GT.",
  "Learned flow quality insufficient": "Chất lượng flow học máy chưa đủ tin cậy để suy luận chuyển động.",
  "Risk is an uncalibrated score, not collision probability": "Risk là điểm chưa hiệu chuẩn, không phải xác suất va chạm.",
  "Runtime measurements use different hardware": "Số đo thời gian chạy đến từ các phần cứng khác nhau.",
};

export function ReportView({ className = "" }: { className?: string }) {
  const [report, setReport] = useState<BenchmarkReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"all" | "detection" | "occupancy" | "flow" | "risk">("all");

  const fetchReport = React.useCallback(async () => {
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
  }, []);

  useEffect(() => {
    let ignore = false;
    const loadInitial = async () => {
      try {
        const res = await fetch("/api/v1/lab/benchmarks");
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: Không thể tải báo cáo số liệu`);
        }
        const data: BenchmarkReportData = await res.json();
        if (!ignore) {
          setReport(data);
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : "Đã có lỗi xảy ra");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    };

    loadInitial();
    return () => {
      ignore = true;
    };
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
      <div className="grid gap-7" role="status" aria-label="Đang tải báo cáo đánh giá">
        <PageHeader eyebrow="03 / EVALUATION" title="Kết quả & giới hạn." description="Một mô hình tốt cần nhiều hơn một con số. Đọc kết quả thực nghiệm cùng phạm vi dữ liệu và giới hạn của từng phép đo." />
        <div className="grid gap-3" aria-hidden="true"><div className="skeleton h-28 rounded-lg" /><div className="skeleton h-12 rounded-lg" /><div className="skeleton h-64 rounded-lg" /></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid gap-7">
        <PageHeader eyebrow="03 / EVALUATION" title="Kết quả & giới hạn." description="Một mô hình tốt cần nhiều hơn một con số. Đọc kết quả thực nghiệm cùng phạm vi dữ liệu và giới hạn của từng phép đo." />
        <div role="alert" className="border-l-2 border-red-600 bg-red-50 px-5 py-4 text-sm text-red-800">
          <p className="font-semibold">Chưa tải được báo cáo</p><p className="mt-1">{error}</p>
          <Button variant="secondary" className="mt-4" onClick={fetchReport}>Thử lại</Button>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-7 text-[var(--foreground)] ${className}`}>
      <PageHeader
        eyebrow="03 / EVALUATION"
        title="Kết quả & giới hạn."
        description="Một mô hình tốt cần nhiều hơn một con số. Đọc kết quả thực nghiệm cùng phạm vi dữ liệu và giới hạn của từng phép đo."
        actions={<Button variant="secondary" onClick={fetchReport}>Làm mới số liệu ↗</Button>}
      />
      <section aria-label="Phạm vi đánh giá" className="report-scope">
        <div className="report-count"><b>{report?.frame_count ?? "—"}</b><span>FRAMES / {report?.split ?? "—"}</span></div>
        <div className="report-limits">
          <h2>Đọc trước khi so sánh</h2>
          <ul>{report?.limitations.map((lim, idx) => <li key={idx}>{limitationLabels[lim] ?? lim}</li>)}</ul>
        </div>
      </section>
      <div className="report-layout">
        <div className="report-filter"><Select label="Nhóm chỉ số" value={activeTab} onChange={event => setActiveTab(event.target.value as typeof activeTab)}>
          <option value="all">Toàn bộ kết quả</option><option value="detection">01 / Detection</option><option value="occupancy">02 / Occupancy</option><option value="flow">03 / Flow</option><option value="risk">04 / Risk</option>
        </Select></div>
        <nav aria-label="Nhóm chỉ số" className="report-index">
          {([
            ["all", "Toàn bộ kết quả", "00"],
            ["detection", "Detection", "01"],
            ["occupancy", "Occupancy", "02"],
            ["flow", "Flow", "03"],
            ["risk", "Risk", "04"],
          ] as const).map(([id, label, number]) => <button key={id} type="button" aria-pressed={activeTab === id} onClick={() => setActiveTab(id)}>{label}<span>{number}</span></button>)}
        </nav>
        <div className="report-content flex flex-col gap-10">
          {(activeTab === "all" || activeTab === "detection") && <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2"><h2>01 / Định vị vật cản</h2><span className="text-[11px] text-[var(--muted)]">nuScenes · 3D detection</span></div>
            <DetectionBenchmarkTable rows={report?.sections?.detection?.data?.rows || []} />
          </section>}
          {(activeTab === "all" || activeTab === "occupancy") && <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2"><h2>02 / Không gian chiếm dụng</h2><span className="text-[11px] text-[var(--muted)]">BEV · 200 × 200 ô · 0.5 m/ô</span></div>
            <OccupancyBenchmarkTable items={report?.sections?.occupancy?.data?.binary_occupancy || []} />
          </section>}
          {(activeTab === "all" || activeTab === "flow") && <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2"><h2>03 / Chuyển động theo thời gian</h2><span className="text-[11px] text-[var(--muted)]">Temporal flow · EPE (m/s)</span></div>
            <FlowBenchmarkTable items={flowItems} />
          </section>}
          {(activeTab === "all" || activeTab === "risk") && <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2"><h2>04 / Trường rủi ro</h2><span className="text-[11px] text-[var(--muted)]">Đối chiếu với Oracle</span></div>
            <RiskBenchmarkTable items={riskItems} />
          </section>}
          <details className="report-provenance">
            <summary>Nguồn dữ liệu & artifact</summary>
            <p className="mt-3 text-xs leading-6">Số liệu được đọc từ các artifact đã lưu. Trang này không chạy inference trong trình duyệt.</p>
            <dl>{report?.sections && Object.entries(report.sections).map(([key, section]) => <div key={key}><dt className="capitalize">{key}</dt><dd>{section?.source || "Chưa có artifact"}</dd></div>)}</dl>
          </details>
        </div>
      </div>
    </div>
  );
}
