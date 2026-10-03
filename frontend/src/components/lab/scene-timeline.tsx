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
  frames, currentIndex, playing, speed, loop, waiting,
  onSeek, onTogglePlay, onSpeedChange, onLoopChange,
}: Props) {
  const validIndex = Math.max(0, Math.min(currentIndex, frames.length - 1));
  const elapsed = frames.length ? frames[validIndex].timestamp_s - frames[0].timestamp_s : 0;
  const duration = frames.length > 1 ? frames[frames.length - 1].timestamp_s - frames[0].timestamp_s : 0;

  return <section aria-label="Dòng thời gian của scene" className="border-b border-white/10 bg-[#102b35] px-4 py-3 text-white">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <p className="text-sm font-semibold">Phát scene theo thời gian</p>
        <p className="text-[11px] text-slate-300">Keyframe nuScenes · không phải video trực tiếp</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-label="Frame trước" title="Frame trước" disabled={currentIndex <= 0} onClick={() => onSeek(currentIndex - 1)} className="rounded-lg border border-white/20 px-3 py-1.5 text-sm hover:bg-white/10 disabled:opacity-40">‹ Trước</button>
        <button type="button" aria-label={playing ? "Tạm dừng" : "Phát"} aria-pressed={playing} disabled={frames.length < 2} onClick={onTogglePlay} className="min-w-28 rounded-lg bg-teal-400 px-4 py-1.5 text-sm font-semibold text-[#08252a] hover:bg-teal-300 disabled:opacity-40">{playing ? "Ⅱ Tạm dừng" : "▶ Phát"}</button>
        <button type="button" aria-label="Frame sau" title="Frame sau" disabled={currentIndex < 0 || currentIndex >= frames.length - 1} onClick={() => onSeek(currentIndex + 1)} className="rounded-lg border border-white/20 px-3 py-1.5 text-sm hover:bg-white/10 disabled:opacity-40">Sau ›</button>
        <label className="ml-1 flex items-center gap-2 text-xs text-slate-300">Tốc độ
          <select aria-label="Tốc độ phát" value={speed} onChange={event => onSpeedChange(Number(event.target.value) as PlaybackSpeed)} className="rounded-lg border border-white/20 bg-[#0b2028] px-2 py-1.5 text-sm text-white">
            <option value={0.5}>0,5×</option><option value={1}>1×</option><option value={2}>2×</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-slate-200"><input type="checkbox" checked={loop} onChange={event => onLoopChange(event.target.checked)} className="accent-teal-400" /> Lặp</label>
      </div>
    </div>
    <div className="mt-2 flex items-center gap-3">
      <span className="w-12 shrink-0 text-xs tabular-nums text-slate-300">{elapsedLabel(elapsed)}</span>
      <input type="range" aria-label="Tua đến frame" aria-valuetext={frames[validIndex] ? `Frame ${frames[validIndex].sample_idx}, ${elapsedLabel(elapsed)}` : "Chưa có frame"} min={0} max={Math.max(0, frames.length - 1)} step={1} value={validIndex} disabled={!frames.length} onChange={event => onSeek(Number(event.target.value))} className="w-full accent-teal-400" />
      <span className="w-12 shrink-0 text-right text-xs tabular-nums text-slate-300">{elapsedLabel(duration)}</span>
    </div>
    <p role="status" className="mt-1 text-[11px] text-slate-300">{frames.length ? `Frame ${validIndex + 1}/${frames.length}` : "Đang tải danh sách frame"}{waiting ? " · Đang đồng bộ dữ liệu…" : playing ? " · Đang phát" : " · Đã tạm dừng"}</p>
  </section>;
}
