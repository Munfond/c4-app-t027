"use client";

import type { Frame } from "@/lib/lab-api";

export type PlaybackSpeed = 0.5 | 1 | 2;

type Props = {
  frames: readonly Frame[];
  currentIndex: number;
  playing: boolean;
  speed: PlaybackSpeed;
  loop: boolean;
  waiting: boolean;
  playDisabled?: boolean;
  onSeek: (index: number) => void;
  onTogglePlay: () => void;
  onSpeedChange: (speed: PlaybackSpeed) => void;
  onLoopChange: (loop: boolean) => void;
};

function elapsedLabel(seconds: number) {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const remainder = (safe % 60).toFixed(1).padStart(4, "0");
  return `${minutes}:${remainder}`;
}

export function SceneTimeline({
  frames, currentIndex, playing, speed, loop, waiting, playDisabled = false,
  onSeek, onTogglePlay, onSpeedChange, onLoopChange,
}: Props) {
  const validIndex = Math.max(0, Math.min(currentIndex, frames.length - 1));
  const elapsed = frames.length ? frames[validIndex].timestamp_s - frames[0].timestamp_s : 0;
  const duration = frames.length > 1 ? frames[frames.length - 1].timestamp_s - frames[0].timestamp_s : 0;

  return <section aria-label="Dòng thời gian của scene" className="transport">
    <div className="transport-main">
      <div className="transport-buttons">
        <button type="button" aria-label="Frame trước" title="Frame trước" disabled={currentIndex <= 0} onClick={() => onSeek(currentIndex - 1)}><svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor"><path d="M3 3h1.5v10H3zM12.5 3 5.5 8l7 5z" /></svg></button>
        <button type="button" className="transport-play" aria-label={playing ? "Tạm dừng" : "Phát"} aria-pressed={playing} title={playDisabled ? "Chưa có đầu ra để phát bài toán này" : playing ? "Tạm dừng" : "Phát scene"} disabled={frames.length < 2 || playDisabled} onClick={onTogglePlay}><svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor">{playing ? <path d="M4 3h3v10H4zM9 3h3v10H9z" /> : <path d="m5 2 9 6-9 6z" />}</svg></button>
        <button type="button" aria-label="Frame sau" title="Frame sau" disabled={currentIndex < 0 || currentIndex >= frames.length - 1} onClick={() => onSeek(currentIndex + 1)}><svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor"><path d="M11.5 3H13v10h-1.5zM3.5 3l7 5-7 5z" /></svg></button>
      </div>
      <div className="transport-track">
        <input type="range" className="transport-range" aria-label="Tua đến frame" aria-valuetext={frames[validIndex] ? `Frame ${frames[validIndex].sample_idx}, ${elapsedLabel(elapsed)}` : "Chưa có frame"} min={0} max={Math.max(0, frames.length - 1)} step={1} value={validIndex} disabled={!frames.length} onChange={event => onSeek(Number(event.target.value))} />
        <div className="transport-times"><span>{elapsedLabel(elapsed)}</span><span>{elapsedLabel(duration)}</span></div>
      </div>
      <div className="transport-options">
        <select aria-label="Tốc độ phát" value={speed} onChange={event => onSpeedChange(Number(event.target.value) as PlaybackSpeed)}><option value={0.5}>0,5×</option><option value={1}>1×</option><option value={2}>2×</option></select>
        <label><input type="checkbox" checked={loop} onChange={event => onLoopChange(event.target.checked)} /> Lặp</label>
      </div>
    </div>
    <div className="transport-meta"><span>{frames.length ? `FRAME ${String(validIndex + 1).padStart(2, "0")} / ${frames.length}` : "ĐANG TẢI FRAME"} · KEYFRAME NUSCENES</span><span role="status">{waiting ? "Đang đồng bộ…" : playing ? "Đang phát" : "Đã tạm dừng"}</span></div>
  </section>;
}
