"use client";

import { useEffect, useMemo, useState } from "react";
import { PointCloudCanvas } from "@/components/viewer/PointCloudCanvas";
import { PerceptionGrid } from "@/components/viewer/PerceptionGrid";
import { loadPerception, type PerceptionOutput, type PerceptionTask } from "@/lib/perception-api";

export function PerceptionWorkspace({ token, task, unavailable = false, onReady, onError }: { token: string; task: PerceptionTask; unavailable?: boolean; onReady: (token: string) => void; onError: () => void }) {
  const [result, setResult] = useState<{ key: string; data?: PerceptionOutput; error?: string } | null>(null);
  const [hiddenClasses, setHiddenClasses] = useState<number[]>([]);
  const key = `${token}:${task}`;
  useEffect(() => {
    if (unavailable) return;
    let active = true;
    void loadPerception(token, task).then(data => {
      if (active) setResult({ key, data });
    }).catch((error: Error) => { if (active) { setResult({ key, error: error.message }); onError(); } });
    return () => { active = false; };
  }, [token, task, key, unavailable, onError]);
  const current = unavailable ? { error: "Missing task outputs", data: undefined } : result?.key === key ? result : null;
  const data = current?.data;
  useEffect(() => { if (data && task !== "seg3d") onReady(token); }, [data, token, task, onReady]);
  const layers = useMemo(() => (data?.classes ?? []).map(c => ({
    id: String(c.id), name: c.name, color: c.color, points: data?.points?.filter(p => p[3] === c.id) ?? [], visible: !hiddenClasses.includes(c.id),
  })), [data, hiddenClasses]);
  if (!current) return <div className="stage-message" role="status">Đang tải {task === "seg3d" ? "phân đoạn 3D" : task === "flow" ? "Flow" : "Occupancy"} của frame…</div>;
  if (!data) return <div className="perception-unavailable" role="status">
    <span className="eyebrow">{task.toUpperCase()} / CHƯA CÓ ĐẦU RA</span>
    <h2>{task === "seg3d" ? "Chưa có phân đoạn 3D cho frame này." : "Kết quả của frame này chưa sẵn sàng."}</h2>
    <p>{task === "seg3d" ? "Seg3D cần nhãn ngữ nghĩa trên từng điểm hoặc voxel. Hình người/xe dựng từ hộp dự đoán và mặt nền nội suy không phải kết quả phân đoạn." : "Chọn frame có bản xuất tương ứng hoặc tải lại sau khi dữ liệu đã được bổ sung."}</p>
    <a href="/benchmarks">Xem chỉ số và giới hạn dữ liệu ↗</a>
  </div>;
  return <div className="perception-workspace">
    <div className="perception-provenance"><strong>{data.model}</strong><span>{data.sensors.join(" + ")}{data.kind ? ` · ${data.kind === "ground_truth" ? "Nhãn tham chiếu" : "Dự đoán"}` : " · Kết quả tính sẵn"}</span></div>
    {task === "seg3d" ? <>
      <div className="seg-class-controls">{data.classes?.map(c => <label key={c.id}><input type="checkbox" checked={!hiddenClasses.includes(c.id)} onChange={event => setHiddenClasses(previous => event.target.checked ? previous.filter(id => id !== c.id) : [...previous, c.id])} />{c.name}</label>)}</div>
      <PointCloudCanvas layers={layers} token={token} onReady={onReady} />
    </> : <PerceptionGrid data={data} />}
    {data.limitations?.length ? <p className="perception-limits">{task === "occupancy" ? "Occupancy BEV 2D · Lớp tĩnh học từ pseudo-GT; lớp free gồm cả vùng chưa quan sát. Không phải bản đồ 3D đầy đủ." : "Flow thử nghiệm · Chất lượng còn hạn chế; mũi tên không phải chuyển động đã xác nhận."}</p> : null}
    <details className="perception-source"><summary>Nguồn kết quả</summary><p>{data.source}</p></details>
  </div>;
}
