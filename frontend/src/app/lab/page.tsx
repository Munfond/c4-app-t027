import { Button } from "@/components/ui/button";
import { PlayIcon } from "@/components/ui/icons";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";

export const metadata = { title: "Lab" };

const legend = [
  ["Car", "bg-[#29c7ad]"],
  ["Pedestrian", "bg-[#f3b74b]"],
  ["Cyclist", "bg-[#da7690]"],
];

export default function LabPage() {
  return (
    <div className="grid gap-6">
      <PageHeader
        actions={
          <Button>
            <PlayIcon className="size-4" />
            Chạy hiển thị
          </Button>
        }
        description="Khám phá từng frame, lớp phát hiện và kết quả fusion trên cùng một không gian."
        title="Perception Lab"
      />

      <section
        aria-label="Bộ lọc dữ liệu"
        className="grid gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)] sm:grid-cols-2 xl:grid-cols-[1.2fr_1fr_1.2fr_0.8fr]"
      >
        <Select defaultValue="scene-0916" label="Scene">
          <option value="scene-0916">scene-0916 · 41 frames</option>
          <option value="scene-0103">scene-0103 · 40 frames</option>
        </Select>
        <Select defaultValue="frame-001" label="Frame">
          <option value="frame-001">001 / 041</option>
          <option value="frame-002">002 / 041</option>
        </Select>
        <Select defaultValue="fused-ours" label="Mô hình">
          <option value="fused-ours">Fused Ours</option>
          <option value="official-lidar">Official LiDAR</option>
          <option value="official-cl">Official Camera + LiDAR</option>
        </Select>
        <Select defaultValue="0.30" label="Ngưỡng điểm">
          <option value="0.30">0.30</option>
          <option value="0.50">0.50</option>
          <option value="0.70">0.70</option>
        </Select>
      </section>

      <div className="grid min-h-[470px] gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <section className="viewer-grid relative flex min-h-[420px] overflow-hidden rounded-[var(--radius)] border border-[#173941] shadow-[var(--shadow)]">
          <div className="absolute inset-x-0 top-0 flex items-center justify-between border-b border-white/10 bg-[#0b2028cc] px-4 py-3 text-xs text-[#b4cdd2] backdrop-blur">
            <span className="font-semibold text-white">Bird&apos;s-eye view</span>
            <span>100 m × 100 m · 0.5 m/cell</span>
          </div>
          <div className="m-auto max-w-sm px-8 text-center">
            <span className="mx-auto grid size-12 place-items-center rounded-2xl border border-[#2b5660] bg-[#14343d] text-[var(--accent)]">
              <PlayIcon className="size-5" />
            </span>
            <h2 className="mt-4 text-base font-bold text-white">
              Khu vực viewer sẵn sàng
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#8eabb2]">
              Component BEV của Người 2 sẽ được gắn vào vùng này qua props dùng chung.
            </p>
          </div>
          <div className="absolute bottom-4 left-4 flex gap-2">
            {legend.map(([label, color]) => (
              <span
                className="rounded-md border border-white/10 bg-[#0b2028cc] px-2 py-1 text-[10px] font-semibold text-[#b4cdd2]"
                key={label}
              >
                <i
                  className={["mr-1.5 inline-block size-1.5 rounded-full", color].join(" ")}
                />
                {label}
              </span>
            ))}
          </div>
        </section>

        <aside className="grid content-start gap-4 rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)]">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--muted)]">
              Chi tiết frame
            </p>
            <h2 className="mt-2 text-base font-bold">scene-0916 · #001</h2>
          </div>
          <dl className="grid grid-cols-2 gap-3">
            {[
              ["Sample token", "ca9a282c…"],
              ["Mô hình", "Fused Ours"],
              ["Đối tượng", "—"],
              ["Score trung bình", "—"],
            ].map(([term, value]) => (
              <div className="rounded-[10px] bg-[var(--surface-subtle)] p-3" key={term}>
                <dt className="text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">
                  {term}
                </dt>
                <dd className="mt-1.5 truncate text-xs font-bold text-[var(--foreground)]">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <div className="border-t border-[var(--line)] pt-4">
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--muted)]">
              Lớp hiển thị
            </p>
            <div className="mt-3 grid gap-2">
              {["3D Detection", "Occupancy", "Flow vector"].map((layer, index) => (
                <label
                  className="flex cursor-pointer items-center justify-between rounded-[10px] px-2 py-2 text-sm font-medium hover:bg-[var(--surface-subtle)]"
                  key={layer}
                >
                  {layer}
                  <input
                    className="size-4 accent-[var(--accent)]"
                    defaultChecked={index === 0}
                    type="checkbox"
                  />
                </label>
              ))}
            </div>
          </div>
        </aside>
      </div>

      <section className="rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)]">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--muted)]">
            Timeline
          </span>
          <span className="font-mono text-xs text-[var(--muted)]">001 / 041</span>
        </div>
        <div className="mt-4 flex items-center gap-1" aria-label="Khung timeline mẫu">
          {Array.from({ length: 20 }).map((_, index) => (
            <span
              className={
                index === 0
                  ? "h-2 flex-1 rounded-full bg-[var(--accent)]"
                  : "h-2 flex-1 rounded-full bg-[var(--line)]"
              }
              key={index}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
