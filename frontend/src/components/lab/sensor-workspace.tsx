"use client";

import { useEffect, useMemo, useState } from "react";
import { loadEnvironmentFrame, type EnvironmentFrame } from "@/lib/lab-frame-cache";
import { loadPerception, type PerceptionOutput } from "@/lib/perception-api";
import { PointCloudCanvas } from "@/components/viewer/PointCloudCanvas";
import { radarReturns, RADAR_SPEED_COLORS } from "@/lib/radar";
import { SEMANTIC_LABELS } from "@/lib/semantic-labels";

export function SensorWorkspace({ token, lidar, radar, segmented = false, onLidarChange, onRadarChange, onSegmentChange, onReady, onError }: { token: string; lidar: boolean; radar: boolean; segmented?: boolean; onLidarChange: (value: boolean) => void; onRadarChange: (value: boolean) => void; onSegmentChange: (value: boolean) => void; onReady: (token: string) => void; onError: () => void }) {
  const [result, setResult] = useState<{ key: string; segmented: boolean; lidar?: EnvironmentFrame; radar?: PerceptionOutput; segmentation?: PerceptionOutput; lidarError?: string; radarError?: string } | null>(null);
  const [hiddenClasses, setHiddenClasses] = useState<number[]>([0]);
  const [pointSize, setPointSize] = useState(.22);
  const [range, setRange] = useState(65);
  const [movingOnly, setMovingOnly] = useState(false);
  const [vectors, setVectors] = useState(true);
  const [selection, setSelection] = useState<{ token: string; index: number } | null>(null);
  const key = `${token}:${segmented}`;
  useEffect(() => {
    let active = true;
    void Promise.allSettled([segmented ? loadPerception(token, "seg3d") : loadEnvironmentFrame(token), loadPerception(token, "radar")]).then(([l, r]) => {
      if (!active) return;
      setResult({ key, segmented,
        ...(l.status === "fulfilled" ? segmented ? { segmentation: l.value as PerceptionOutput } : { lidar: l.value as EnvironmentFrame } : { lidarError: segmented ? "Chưa có Seg3D của frame này. Chọn Điểm đo để xem LiDAR gốc." : "LiDAR của frame này chưa sẵn sàng." }),
        ...(r.status === "fulfilled" ? { radar: r.value } : { radarError: "Chưa có bản xuất Radar của frame này." }),
      });
    });
    return () => { active = false; };
  }, [token, segmented, key]);
  const settled = result?.key === key;
  const current = result?.segmented === segmented ? result : null;
  const displayedToken = current?.key.split(":")[0] ?? "";
  useEffect(() => {
    if (settled && ((lidar && current?.lidarError) || (radar && current?.radarError))) onError();
  }, [settled, lidar, radar, current, onError]);
  const echoes = useMemo(() => radarReturns(current?.radar?.points ?? [], range, movingOnly), [current?.radar, range, movingOnly]);
  const radarPoints = useMemo(() => echoes.map(echo => echo.point), [echoes]);
  const selected = echoes.find(echo => selection?.token === displayedToken && echo.index === selection.index) ?? echoes[0];
  const groups = useMemo(() => {
    const grouped = new Map<number, number[][]>();
    current?.segmentation?.classes?.forEach(c => grouped.set(c.id, []));
    current?.segmentation?.points?.forEach(point => grouped.get(point[3])?.push(point));
    return grouped;
  }, [current]);
  const layers = useMemo(() => [
    ...(segmented ? (current?.segmentation?.classes ?? []).map(c => ({ id: `semantic-${c.id}`, name: SEMANTIC_LABELS[c.name] ?? c.name, color: c.color, points: groups.get(c.id) ?? [], visible: lidar && !hiddenClasses.includes(c.id), size: pointSize })) : [{ id: "lidar", name: "LiDAR", color: "#8dc7c4", points: current?.lidar?.points ?? [], visible: lidar, size: .14 }]),
    { id: "radar", name: "Radar", color: "#ffbb72", points: radarPoints, visible: radar, size: .65, colorBySpeed: true, vectors, selectedIndex: selected ? echoes.indexOf(selected) : undefined },
  ], [current, lidar, radar, segmented, groups, hiddenClasses, pointSize, radarPoints, vectors, selected, echoes]);
  return <div className="sensor-workspace" aria-busy={!settled} data-frame-token={current?.key.split(":")[0]}>
    <div className="sensor-view-toolbar">
      <fieldset className="sensor-visibility"><legend className="sr-only">Cảm biến hiển thị</legend>
        <label><input type="checkbox" checked={lidar} onChange={event => onLidarChange(event.target.checked)} /><i style={{ background: "#8dc7c4" }} />LiDAR</label>
        <label><input type="checkbox" checked={radar} onChange={event => onRadarChange(event.target.checked)} /><i style={{ background: "#ffbb72" }} />Radar</label>
      </fieldset>
      <label className="sensor-color-mode">Màu LiDAR<select aria-label="Màu LiDAR" disabled={!lidar} value={segmented ? "segmented" : "measured"} onChange={event => onSegmentChange(event.target.value === "segmented")}><option value="measured">Điểm đo</option><option value="segmented">Phân đoạn</option></select></label>
    </div>
    {lidar && segmented && current?.segmentation ? <details className="sensor-semantics"><summary>Phân đoạn LiDAR · {current.segmentation.points?.length.toLocaleString("vi-VN")} điểm · tùy chỉnh lớp</summary>
      <div className="semantic-summary"><div><span>LIDAR / DỰ ĐOÁN SEG3D</span><strong>{current.segmentation.points?.length.toLocaleString("vi-VN")} <small>điểm · cùng frame</small></strong></div><label>Kích thước điểm<input type="range" min="0.1" max="0.4" step="0.02" value={pointSize} onChange={event => setPointSize(Number(event.target.value))} /></label></div>
      <details className="sensor-class-filter"><summary>Các lớp phân đoạn · bật / tắt lớp</summary><div className="seg-class-controls" role="group" aria-label="Lớp phân đoạn LiDAR">{current.segmentation.classes?.filter(c => groups.get(c.id)?.length).map(c => <label key={c.id}><input type="checkbox" checked={!hiddenClasses.includes(c.id)} onChange={event => setHiddenClasses(previous => event.target.checked ? previous.filter(id => id !== c.id) : [...previous, c.id])} /><i style={{ background: c.color }} />{SEMANTIC_LABELS[c.name] ?? c.name}</label>)}</div></details>
      <p className="sensor-seg-source">{current.segmentation.model} · SemanticKITTI → nuScenes, thử nghiệm. Radar giữ màu điểm đo; chưa được gán lớp ngữ nghĩa.</p>
    </details> : null}
    <PointCloudCanvas layers={layers} token={settled ? token : ""} onReady={settled ? onReady : undefined} showLegend={!segmented || !lidar} onPointSelect={(layer, index) => {
      if (layer === "radar" && echoes[index]) setSelection({ token: displayedToken, index: echoes[index].index });
    }} />
    {radar && current?.radar ? <details className="sensor-radar-details">
      <summary><span>Radar · {echoes.length}/{current.radar.points?.length ?? 0} điểm</span><span>{selected ? `#${selected.index + 1} · ${selected.distance.toFixed(1)} m · ${selected.speed.toFixed(1)} m/s` : "Không có điểm phù hợp"}</span><span className="radar-details-hint">Số đo & bộ lọc</span></summary>
      <div className="sensor-radar-options">
        <label>Bán kính<select aria-label="Bán kính Radar" value={range} onChange={event => setRange(Number(event.target.value))}>{[25, 50, 65].map(value => <option key={value} value={value}>{value} m</option>)}</select></label>
        <label><input type="checkbox" checked={vectors} onChange={event => setVectors(event.target.checked)} />Vector vận tốc · 1 s</label>
        <label><input type="checkbox" checked={movingOnly} onChange={event => setMovingOnly(event.target.checked)} />Chỉ ≥ 0,5 m/s</label>
        <label className="sensor-return-select">Điểm đo<select aria-label="Số đo điểm Radar" disabled={!echoes.length} value={selected?.index ?? ""} onChange={event => setSelection({ token: displayedToken, index: Number(event.target.value) })}>{echoes.length ? echoes.map(echo => <option key={echo.index} value={echo.index}>#{echo.index + 1} · {echo.distance.toFixed(1)} m · {echo.speed.toFixed(1)} m/s</option>) : <option value="">Không có điểm</option>}</select></label>
        {selected ? <p className="sensor-return-position">{selected.point[0] >= 0 ? "Trước" : "Sau"} {Math.abs(selected.point[0]).toFixed(2)} m · {selected.point[1] >= 0 ? "trái" : "phải"} {Math.abs(selected.point[1]).toFixed(2)} m · v trước/trái {selected.point[3].toFixed(2)} / {selected.point[4].toFixed(2)} m/s</p> : <p className="sensor-return-position" role="status">Không có điểm phù hợp. Tăng bán kính hoặc bỏ lọc tốc độ.</p>}
        <div className="sensor-radar-key">{["< 0,5", "0,5–2", "> 2 m/s"].map((label, index) => <span key={label}><i style={{ background: RADAR_SPEED_COLORS[index] }} />{label}</span>)}</div>
        <p className="sensor-radar-note">Radar: điểm phản xạ, màu theo tốc độ đã bù chuyển động xe. Vector v × 1 s không phải quỹ đạo dự báo; ẩn lớp không chạy lại mô hình.</p>
      </div>
    </details> : null}
    {!current ? <div role="status" className="stage-message">Đang đồng bộ LiDAR và Radar…</div> : null}
    {(lidar && current?.lidarError) || (radar && current?.radarError) ? <p role="status" className="sensor-warning">{[lidar && current?.lidarError, radar && current?.radarError].filter(Boolean).join(" ")}</p> : null}
    {current && !layers.some(layer => layer.visible && layer.points.length) && !(lidar && current.lidarError) && !(radar && current.radarError) ? <div className="sensor-empty" role="status">Không có lớp điểm đang hiển thị. Bật LiDAR, Radar hoặc một lớp phân đoạn để tiếp tục quan sát.</div> : null}
  </div>;
}
