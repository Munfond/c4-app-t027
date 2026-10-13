"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { CameraCard } from "@/components/camera/CameraCard";
import { CameraPanel } from "@/components/camera";
import { Select } from "@/components/ui/select";
import { BevViewer } from "@/components/viewer";
import { apiJson, detectionUrl, modelLabel, mvpModels, type DetectionFrame, type Frame, type ModelInfo, type Scene } from "@/lib/lab-api";
import { detectionFrames, environmentFrames, loadEnvironmentFrame } from "@/lib/lab-frame-cache";
import { clearPerceptionCache, loadPerception, type PerceptionTask, type TaskStatus } from "@/lib/perception-api";
import { adaptDetectionFrame } from "@/lib/viewer";
import { RiskHeatmap } from "./risk-heatmap";
import { SceneTimeline, type PlaybackSpeed } from "./scene-timeline";

const SpatialViewer = dynamic(() => import("@/components/viewer/SpatialViewer").then(m => m.SpatialViewer), { ssr: false });
const SensorWorkspace = dynamic(() => import("./sensor-workspace").then(m => m.SensorWorkspace), { ssr: false });
const PerceptionWorkspace = dynamic(() => import("./perception-workspace").then(m => m.PerceptionWorkspace), { ssr: false });

type Workspace = "sensors" | "results" | "risk";
const WORKSPACES = [{ id: "sensors", number: "01", title: "Cảm biến", note: "Quan sát đầu vào" }, { id: "results", number: "02", title: "Kết quả mô hình", note: "Hiểu không gian" }, { id: "risk", number: "03", title: "Risk", note: "Ước lượng rủi ro" }] as const;
const TASKS = [{ id: "detection", label: "Detection 3D" }, { id: "seg3d", label: "Seg3D · Phân đoạn 3D" }, { id: "occupancy", label: "Occupancy" }, { id: "flow", label: "Flow" }] as const;

export function LabWorkspace() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [scene, setScene] = useState("");
  const [token, setToken] = useState("");
  const [model, setModel] = useState("");
  const [threshold, setThreshold] = useState(0.5);
  const [detections, setDetections] = useState<DetectionFrame | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loadedKey, setLoadedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [spatialMode, setSpatialMode] = useState<"bev" | "3d">("3d");
  const [settingsExpanded, setSettingsExpanded] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [workspace, setWorkspace] = useState<Workspace>("sensors");
  const [task, setTask] = useState<"detection" | PerceptionTask>("detection");
  const [sensorView, setSensorView] = useState<"points" | "camera">("points");
  const [showLidar, setShowLidar] = useState(true);
  const [showRadar, setShowRadar] = useState(true);
  const [segmentLidar, setSegmentLidar] = useState(false);
  const [taskStatus, setTaskStatus] = useState<TaskStatus[]>([]);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [loop, setLoop] = useState(false);
  const [spatialReadyToken, setSpatialReadyToken] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      apiJson<{ items: Scene[] }>("/api/v1/lab/scenes", controller.signal),
      apiJson<{ items: ModelInfo[] }>("/api/v1/lab/models", controller.signal),
    ]).then(([sceneData, modelData]) => {
      setScenes(sceneData.items);
      const demoModels = mvpModels(modelData.items);
      setModels(demoModels);
      setScene(sceneData.items[0]?.id ?? "");
      setModel(demoModels.find((item) => item.id === "fused")?.id ?? demoModels[0]?.id ?? "");
    }).catch((reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); }).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!scene) return;
    const controller = new AbortController();
    void apiJson<{ items: Frame[] }>(`/api/v1/lab/scenes/${encodeURIComponent(scene)}/frames`, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        const ordered = [...data.items].sort((a, b) => a.timestamp_s - b.timestamp_s);
        setFrames(ordered);
        setToken(ordered[0]?.sample_token ?? "");
      })
      .catch((reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); });
    return () => controller.abort();
  }, [scene, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    void apiJson<{ items: TaskStatus[] }>("/api/v1/lab/perception/tasks", controller.signal)
      .then(data => setTaskStatus(data.items)).catch(() => { /* Frame requests provide the detailed availability state. */ });
    return () => controller.abort();
  }, [refresh]);

  const loadDetections = () => {
    setPlaying(false);
    detectionFrames.clear();
    environmentFrames.clear();
    clearPerceptionCache();
    setSpatialReadyToken(null);
    setRefresh(value => value + 1);
  };

  useEffect(() => {
    if (!token || !model || workspace !== "results" || task !== "detection") return;
    let active = true;
    const key = `${token}:${model}:${threshold}:${refresh}`;
    void detectionFrames.get(key, () => apiJson<DetectionFrame>(detectionUrl(token, model, threshold)))
      .then(data => {
        if (!active) return;
        setDetections(data);
        setLoadedKey(key);
        setError("");
      })
      .catch((reason: Error) => {
        if (active) { setError(reason.message); setPlaying(false); }
      });
    return () => { active = false; };
  }, [token, model, threshold, refresh, workspace, task]);

  const activeFrame = frames.find((item) => item.sample_token === token);
  const currentIndex = frames.findIndex((item) => item.sample_token === token);
  const nextFrame = currentIndex >= 0 ? frames[currentIndex + 1] : undefined;
  const upcomingFrame = nextFrame ?? (loop && frames.length > 1 ? frames[0] : undefined);
  const ready = loadedKey === `${token}:${model}:${threshold}:${refresh}` && activeFrame?.scene === scene;
  const viewerFrame = useMemo(() => detections && ready ? adaptDetectionFrame(detections) : null, [detections, ready]);
  const detectionActive = workspace === "results" && task === "detection";
  const readyForPlayback = activeFrame?.scene === scene && (detectionActive && spatialMode === "bev" ? ready : spatialReadyToken === token);

  useEffect(() => {
    if (!playing || !readyForPlayback || currentIndex < 0) return;
    const atEnd = currentIndex === frames.length - 1;
    const intervalSeconds = atEnd ? 0.5 : frames[currentIndex + 1].timestamp_s - frames[currentIndex].timestamp_s;
    const delay = Math.max(120, Math.min(2000, intervalSeconds * 1000 / speed));
    const timer = window.setTimeout(() => {
      if (atEnd && !loop) setPlaying(false);
      else setToken(frames[atEnd ? 0 : currentIndex + 1].sample_token);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [playing, readyForPlayback, currentIndex, frames, speed, loop]);

  useEffect(() => {
    const pauseWhenHidden = () => { if (document.hidden) setPlaying(false); };
    const pauseForExperiment = () => setPlaying(false);
    document.addEventListener("visibilitychange", pauseWhenHidden);
    window.addEventListener("p027-pause-lab", pauseForExperiment);
    return () => {
      document.removeEventListener("visibilitychange", pauseWhenHidden);
      window.removeEventListener("p027-pause-lab", pauseForExperiment);
    };
  }, []);

  useEffect(() => {
    const leaveFocus = (event: KeyboardEvent) => { if (event.key === "Escape") setFocusMode(false); };
    window.addEventListener("keydown", leaveFocus);
    return () => window.removeEventListener("keydown", leaveFocus);
  }, []);

  useEffect(() => {
    if (!readyForPlayback || !upcomingFrame) return;
    const next = upcomingFrame.sample_token;
    if (detectionActive && model) {
      const key = `${next}:${model}:${threshold}:${refresh}`;
      void detectionFrames.get(key, () => apiJson<DetectionFrame>(detectionUrl(next, model, threshold))).catch(() => {});
      if (spatialMode === "3d") void loadEnvironmentFrame(next).catch(() => {});
    } else if (workspace === "sensors" && sensorView === "points") {
      if (segmentLidar) void loadPerception(next, "seg3d").catch(() => {});
      else void loadEnvironmentFrame(next).catch(() => {});
      void loadPerception(next, "radar").catch(() => {});
    } else if (workspace === "results" && task !== "detection") {
      void loadPerception(next, task).catch(() => {});
    }
  }, [readyForPlayback, upcomingFrame, detectionActive, workspace, sensorView, segmentLidar, task, model, threshold, refresh, spatialMode]);

  const seek = (index: number) => {
    const selected = frames[index];
    if (!selected) return;
    setPlaying(false);
    setToken(selected.sample_token);
  };

  const togglePlayback = () => {
    if (playing) { setPlaying(false); return; }
    if (currentIndex === frames.length - 1 && frames.length > 1) setToken(frames[0].sample_token);
    setPlaying(true);
  };
  const stopOnSpatialError = useCallback(() => setPlaying(false), []);
  const nearest = viewerFrame?.detections.length
    ? Math.min(...viewerFrame.detections.map(item => Math.hypot(item.center.forward, item.center.left)))
    : null;

  const changeWorkspace = (next: Workspace) => {
    setPlaying(false); setSpatialReadyToken(null); setWorkspace(next); setError("");
  };
  const changeTask = (next: typeof task) => {
    setPlaying(false); setSpatialReadyToken(null); setError(""); setTask(next);
  };
  const currentToken = activeFrame?.scene === scene ? token : "";
  const availability = taskStatus.find(item => item.id === task);
  const modelSensors = models.find(item => item.id === model)?.sensors.join(" + ") ?? "";

  return <div>
    <header className="lab-heading">
      <div><p className="eyebrow">PERCEPTION LAB / T27</p><h1>Từ quan sát <span>đến hiểu không gian.</span></h1></div>
      <p className="lab-heading-note">Một scene, một dòng thời gian.<br />Đối chiếu tín hiệu, dự đoán và rủi ro.</p>
    </header>
    <div className="workspace-navigation" role="tablist" aria-label="Các bước khám phá Lab">
      {WORKSPACES.map((item, index) => <button type="button" role="tab" id={`workspace-${item.id}`} aria-controls="lab-workspace-panel" aria-selected={workspace === item.id} tabIndex={workspace === item.id ? 0 : -1} key={item.id} onClick={() => changeWorkspace(item.id)} onKeyDown={event => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % WORKSPACES.length;
        else if (event.key === "ArrowLeft") next = (index + WORKSPACES.length - 1) % WORKSPACES.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = WORKSPACES.length - 1;
        else return;
        event.preventDefault(); changeWorkspace(WORKSPACES[next].id);
        document.getElementById(`workspace-${WORKSPACES[next].id}`)?.focus();
      }}><span>{item.number}</span><div><strong>{item.title}</strong><small>{item.note}</small></div><span aria-hidden="true">↗</span></button>)}
    </div>
    {error && detectionActive ? <div role="alert" className="mb-4 border-l-2 border-red-600 bg-red-50 px-4 py-3 text-sm text-red-800">Không thể tải dữ liệu: {error}</div> : null}
    <div id="lab-workspace-panel" role="tabpanel" aria-labelledby={`workspace-${workspace}`} className="lab-layout" data-focus={focusMode}>
      <aside className="lab-inspector" data-expanded={settingsExpanded} aria-label="Thiết lập dữ liệu">
        <div className="inspector-heading"><h2>Thiết lập quan sát</h2><span>FRAME / SYNC</span></div>
        <button type="button" className="inspector-toggle" aria-expanded={settingsExpanded} aria-controls="lab-inspector-fields" onClick={() => setSettingsExpanded(value => !value)}>
          <span>{scene || "Đang tải scene"}<small>{WORKSPACES.find(item => item.id === workspace)?.title}</small></span>
          <span>{settingsExpanded ? "ĐÓNG −" : "THIẾT LẬP +"}</span>
        </button>
        <div className="inspector-fields" id="lab-inspector-fields">
          <Select label="Scene" value={scene} onChange={event => {
            if (event.target.value === scene) return;
            setPlaying(false); setFrames([]); setToken(""); setSpatialReadyToken(null); setScene(event.target.value);
          }} disabled={!scenes.length}>
            {scenes.map(item => <option key={item.id} value={item.id}>{item.id} / {item.frame_count} frames</option>)}
          </Select>
          <Select label="Frame · chung cho mọi góc nhìn" value={token} onChange={event => seek(frames.findIndex(item => item.sample_token === event.target.value))} disabled={!frames.length || activeFrame?.scene !== scene}>
            {frames.map(item => <option key={item.sample_token} value={item.sample_token}>#{item.sample_idx} / +{(item.timestamp_s - frames[0].timestamp_s).toFixed(1)}s</option>)}
          </Select>
          {workspace === "results" ? <>
            <Select label="Bài toán" value={task} onChange={event => changeTask(event.target.value as typeof task)}>
              {TASKS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
            </Select>
            {detectionActive ? <>
              <div className="inspector-model"><Select label="Mô hình Detection" title={modelLabel(model)} value={model} onChange={event => { setPlaying(false); setModel(event.target.value); }} disabled={!models.length}>
                {models.map(item => <option key={item.id} value={item.id}>{modelLabel(item).split(" · ")[0]}</option>)}
              </Select><p>Đầu vào mô hình: {modelSensors || "Đang tải…"}</p></div>
              <fieldset className="threshold-selector"><legend>Ngưỡng điểm dự đoán</legend><div className="threshold-options">
                {[0.3, 0.5, 0.7].map(value => <button key={value} type="button" aria-pressed={threshold === value} onClick={() => { setPlaying(false); setThreshold(value); }}>{value.toFixed(2)}</button>)}
              </div></fieldset>
            </> : <p className="task-availability">{availability ? `${availability.frame_count}/${availability.total_frames} frame có đầu ra ${TASKS.find(item => item.id === task)?.label.split(" · ")[0]}.` : "Đang kiểm tra đầu ra theo frame…"}</p>}
          </> : workspace === "sensors" ? <p className="task-availability">{sensorView === "points" ? "Bật/tắt LiDAR và Radar ngay trên khung điểm. Chọn Phân đoạn để tô màu LiDAR theo lớp ngữ nghĩa." : "Camera 360° cùng frame với LiDAR và Radar."}</p> : <p className="task-availability">Risk dùng nguồn Classical LiDAR hoặc Oracle tham chiếu; độc lập với mô hình Detection đang chọn.</p>}
        </div>
        {detectionActive ? <dl className="inspector-measures">
          <div><dt>Vật cản hiển thị</dt><dd>{viewerFrame ? viewerFrame.detections.length : "—"}</dd></div>
          <div><dt>Tâm gần nhất</dt><dd>{nearest !== null ? nearest.toFixed(1) : "—"}<small>m</small></dd></div>
        </dl> : null}
        <div className="inspector-note"><strong>{workspace === "sensors" ? "DỮ LIỆU QUAN SÁT" : task === "seg3d" && workspace === "results" ? "SEGMENTATION / 3D" : "PRECOMPUTED / MINI VAL"}</strong>
          {workspace === "sensors" ? "LiDAR và Radar là các điểm đo, cùng hệ tọa độ xe. Khoảng trống chưa có điểm không đồng nghĩa với đường thông thoáng." : workspace === "risk" ? "Điểm rủi ro chưa hiệu chuẩn, không phải xác suất va chạm." : task === "seg3d" ? "Seg3D gán lớp ngữ nghĩa cho từng điểm/voxel. Hình đại diện từ box không phải kết quả phân đoạn." : task === "detection" ? "Kết quả đã tính sẵn. Nền LiDAR tham chiếu được hiển thị độc lập với đầu vào mô hình." : "Kết quả của mô hình LiDAR + Radar đã tính sẵn, gắn với frame đang chọn."}
        </div>
        {currentToken && !(workspace === "sensors" && sensorView === "camera") ? <div className="inspector-camera"><p>CAMERA THAM CHIẾU / CÙNG FRAME</p><CameraCard sampleToken={currentToken} channel="CAM_FRONT" label="Phía trước" onFocus={() => { changeWorkspace("sensors"); setSensorView("camera"); }} /></div> : null}
        <button type="button" className="inspector-refresh" disabled={loading} onClick={loadDetections}><span>Tải lại dữ liệu</span><span aria-hidden="true">↻</span></button>
      </aside>
      <section aria-label="Quan sát và kết quả đồng bộ" className="lab-stage">
        <div className="stage-toolbar">
          <div className="stage-context"><i aria-hidden="true" /><strong>{scene || "Đang tải"}</strong><span>/</span><span>{currentToken ? `FRAME ${String(activeFrame!.sample_idx).padStart(3, "0")}` : "—"}</span></div>
          <div className="stage-tools">
            {workspace === "sensors" ? <div className="view-switch" role="group" aria-label="Dữ liệu cảm biến">
              <button type="button" aria-pressed={sensorView === "points"} onClick={() => { setPlaying(false); setSpatialReadyToken(null); setSensorView("points"); }}>LiDAR + Radar</button>
              <button type="button" aria-pressed={sensorView === "camera"} onClick={() => { setPlaying(false); setSpatialReadyToken(null); setSensorView("camera"); }}>Camera 360°</button>
            </div> : detectionActive ? <div className="view-switch" role="group" aria-label="Cách xem Detection">
              <button type="button" aria-pressed={spatialMode === "3d"} onClick={() => { setSpatialReadyToken(null); setSpatialMode("3d"); }}>Hình đại diện 3D</button>
              <button type="button" aria-pressed={spatialMode === "bev"} onClick={() => setSpatialMode("bev")}>BEV 2D</button>
            </div> : <span className="stage-task-label">{workspace === "risk" ? "RISK / REFERENCE" : TASKS.find(item => item.id === task)?.label}</span>}
            <button type="button" className="focus-toggle" aria-label={focusMode ? "Thu gọn bản đồ" : "Mở rộng bản đồ"} aria-pressed={focusMode} onClick={() => setFocusMode(value => !value)} title="Nhấn Escape để thu gọn.">
              <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.3"><path d="M7 3H3v4m10-4h4v4M3 13v4h4m10-4v4h-4" /></svg><span>{focusMode ? "Thu gọn" : "Tập trung"}</span>
            </button>
          </div>
        </div>
        {workspace === "results" ? <div className="mobile-task-selector"><Select id="mobile-perception-task" label="Bài toán hiển thị" value={task} onChange={event => changeTask(event.target.value as typeof task)}>
          {TASKS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
        </Select></div> : null}
        <div className="stage-canvas" data-content={workspace === "sensors" && sensorView === "camera" ? "camera" : workspace === "risk" ? "risk" : "spatial"}>
          {!currentToken ? <div role="status" className="stage-message">{error || "Đang tải danh sách frame…"}</div>
            : workspace === "sensors" ? sensorView === "camera" ? <CameraPanel sampleToken={currentToken} onFrameReady={setSpatialReadyToken} /> : <SensorWorkspace key={refresh} token={currentToken} lidar={showLidar} radar={showRadar} segmented={segmentLidar} onLidarChange={setShowLidar} onRadarChange={setShowRadar} onSegmentChange={value => { setPlaying(false); setSpatialReadyToken(null); setSegmentLidar(value); }} onReady={setSpatialReadyToken} onError={stopOnSpatialError} />
            : workspace === "risk" ? <RiskHeatmap sampleToken={currentToken} onFrameReady={setSpatialReadyToken} onFrameError={stopOnSpatialError} />
            : task !== "detection" ? <PerceptionWorkspace key={refresh} token={currentToken} task={task} unavailable={availability?.frame_count === 0} onReady={setSpatialReadyToken} onError={stopOnSpatialError} />
            : spatialMode === "3d" ? <SpatialViewer key={refresh} frame={viewerFrame} sampleToken={currentToken} nextToken={upcomingFrame?.sample_token} requestError={error || null} onFrameReady={setSpatialReadyToken} onFrameError={stopOnSpatialError} />
            : <BevViewer error={error || null} frame={viewerFrame} isLoading={loading || (!ready && !error)} />}
        </div>
        <div className="stage-provenance">{workspace === "sensors" ? "ĐIỂM ĐO / KHÔNG PHẢI DỰ ĐOÁN" : workspace === "risk" ? "RISK THAM CHIẾU / CHƯA HIỆU CHUẨN" : detectionActive ? `VẬT CẢN: ${modelLabel(model).split(" · ")[0]} · ${modelSensors} / NỀN: LIDAR THAM CHIẾU` : `${task.toUpperCase()} / ĐẦU RA THEO FRAME`}</div>
        <SceneTimeline frames={frames} currentIndex={currentIndex} playing={playing} speed={speed} loop={loop} waiting={playing && !readyForPlayback} playDisabled={workspace === "results" && task !== "detection" && availability?.frame_count === 0} onSeek={seek} onTogglePlay={togglePlayback} onSpeedChange={setSpeed} onLoopChange={setLoop} />
      </section>
    </div>
    <div className="lab-caption"><span><strong>Giới hạn dữ liệu.</strong> Mini scenes có mặt trong tập train official; kết quả dành cho trực quan hóa, không phải benchmark công bằng.</span><a href="/compare">So sánh hai mô hình ↗</a></div>
  </div>;
}
