import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Đánh giá" };

const rows = [
  ["Official LiDAR", "LiDAR", "Precomputed", "—"],
  ["Official Camera + LiDAR", "Camera + LiDAR", "Precomputed", "—"],
  ["Fused Ours", "Late fusion", "Precomputed", "—"],
];

export default function BenchmarksPage() {
  return (
    <div className="grid gap-6">
      <PageHeader
        actions={<Button variant="secondary">Xuất báo cáo</Button>}
        description="Theo dõi nguồn mô hình, phạm vi dữ liệu và chỉ số đánh giá đã công bố."
        title="Benchmarks"
      />
      <section className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-white shadow-[var(--shadow)]">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
          <div>
            <h2 className="text-sm font-bold">Model registry</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Bảng nền để Người 3 tích hợp benchmark API và report.
            </p>
          </div>
          <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-bold text-[var(--accent-strong)]">
            3 mô hình
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-left">
            <thead className="bg-[var(--surface-subtle)] text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--muted)]">
              <tr>
                {["Tên mô hình", "Nguồn cảm biến", "Trạng thái", "mAP"].map(
                  (header) => (
                    <th className="px-5 py-3" key={header}>
                      {header}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)] text-sm">
              {rows.map((row) => (
                <tr className="transition hover:bg-[#f8fafa]" key={row[0]}>
                  {row.map((cell, index) => (
                    <td
                      className={
                        index === 0
                          ? "px-5 py-4 font-semibold"
                          : "px-5 py-4 text-[var(--muted)]"
                      }
                      key={cell}
                    >
                      {index === 2 ? (
                        <span className="inline-flex items-center gap-2">
                          <i className="size-1.5 rounded-full bg-[var(--accent)]" />
                          {cell}
                        </span>
                      ) : (
                        cell
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
