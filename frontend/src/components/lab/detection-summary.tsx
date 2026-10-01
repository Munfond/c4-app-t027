import type { DetectionFrame } from "@/lib/lab-api";

export function DetectionSummary({ data }: { data: DetectionFrame | null }) {
  if (!data) {
    return <p className="m-auto text-sm text-[#8eabb2]">Chọn frame để tải kết quả phát hiện.</p>;
  }

  const groups = Object.entries(
    data.boxes.reduce<Record<string, number>>((counts, box) => {
      counts[box.class_name] = (counts[box.class_name] ?? 0) + 1;
      return counts;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex h-full flex-col p-5 pt-16 text-white">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Đối tượng" value={String(data.boxes.length)} />
        <Stat label="Lớp" value={String(groups.length)} />
        <Stat label="Mô hình" value={data.model} />
        <Stat label="Chế độ" value={data.mode} />
      </div>
      <div className="mt-5 overflow-auto rounded-xl border border-white/10 bg-[#0b2028cc]">
        <table className="w-full min-w-[560px] text-left text-xs">
          <thead className="text-[#88a9b0]"><tr>{["Lớp", "Score", "x", "y", "Vận tốc"].map((x) => <th className="px-3 py-2" key={x}>{x}</th>)}</tr></thead>
          <tbody className="divide-y divide-white/10">
            {data.boxes.slice(0, 30).map((box, index) => (
              <tr key={`${box.class_name}-${index}`}>
                <td className="px-3 py-2 font-semibold">{box.class_name}</td>
                <td className="px-3 py-2">{box.score.toFixed(3)}</td>
                <td className="px-3 py-2">{box.x.toFixed(1)} m</td>
                <td className="px-3 py-2">{box.y.toFixed(1)} m</td>
                <td className="px-3 py-2">{Math.hypot(box.vx, box.vy).toFixed(1)} m/s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/10 bg-[#14343d] p-3"><p className="text-[10px] uppercase tracking-wider text-[#88a9b0]">{label}</p><p className="mt-1 truncate text-sm font-bold">{value}</p></div>;
}
