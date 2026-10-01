import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";

export const metadata = { title: "So sánh" };

export default function ComparePage() {
  return (
    <div className="grid gap-6">
      <PageHeader
        actions={<Button variant="secondary">Đồng bộ camera</Button>}
        description="Đặt hai mô hình cạnh nhau trên cùng scene, frame và ngưỡng điểm."
        title="So sánh mô hình"
      />
      <section className="grid gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-white p-4 shadow-[var(--shadow)] md:grid-cols-3">
        <Select defaultValue="scene-0916" label="Scene">
          <option value="scene-0916">scene-0916</option>
          <option value="scene-0103">scene-0103</option>
        </Select>
        <Select defaultValue="official-lidar" label="Mô hình A">
          <option value="official-lidar">Official LiDAR</option>
          <option value="our-lidar">Our LiDAR</option>
        </Select>
        <Select defaultValue="fused-ours" label="Mô hình B">
          <option value="fused-ours">Fused Ours</option>
          <option value="official-cl">Official Camera + LiDAR</option>
        </Select>
      </section>
      <div className="grid min-h-[500px] gap-5 lg:grid-cols-2">
        {[
          ["Mô hình A", "Official LiDAR"],
          ["Mô hình B", "Fused Ours"],
        ].map(([label, model]) => (
          <section
            className="viewer-grid flex min-h-[380px] flex-col overflow-hidden rounded-[var(--radius)] border border-[#173941] shadow-[var(--shadow)]"
            key={label}
          >
            <div className="flex items-center justify-between border-b border-white/10 bg-[#0b2028cc] px-4 py-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-[#88a9b0]">
                {label}
              </span>
              <span className="text-sm font-bold text-white">{model}</span>
            </div>
            <p className="m-auto max-w-xs px-6 text-center text-sm leading-6 text-[#8eabb2]">
              Vùng tích hợp viewer so sánh của Người 2.
            </p>
          </section>
        ))}
      </div>
    </div>
  );
}
