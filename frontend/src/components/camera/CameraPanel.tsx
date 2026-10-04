"use client";

import React, { useCallback, useRef, useState } from "react";
import { useNearViewport } from "@/lib/use-near-viewport";
import { CameraCard } from "./CameraCard";

export interface CameraPanelProps {
  sampleToken: string;
  className?: string;
  onFrameReady?: (token: string) => void;
}

export const NUSCENES_CAMERAS = [
  { channel: "CAM_FRONT_LEFT", label: "Front Left", pos: "front-left" },
  { channel: "CAM_FRONT", label: "Front Center", pos: "front" },
  { channel: "CAM_FRONT_RIGHT", label: "Front Right", pos: "front-right" },
  { channel: "CAM_BACK_LEFT", label: "Back Left", pos: "back-left" },
  { channel: "CAM_BACK", label: "Back Center", pos: "back" },
  { channel: "CAM_BACK_RIGHT", label: "Back Right", pos: "back-right" },
] as const;

export function CameraPanel({ sampleToken, className = "", onFrameReady }: CameraPanelProps) {
  const [viewMode, setViewMode] = useState<"grid" | "focus">("grid");
  const [selectedChannel, setSelectedChannel] = useState<string>("CAM_FRONT");
  const [refreshSeed, setRefreshSeed] = useState(0);
  const { ref, near } = useNearViewport<HTMLDivElement>();
  const settled = useRef<{ token: string; channels: Set<string> }>({ token: "", channels: new Set() });
  const onFrameSettled = useCallback((token: string, channel: string) => {
    if (token !== sampleToken) return;
    if (settled.current.token !== token) settled.current = { token, channels: new Set() };
    settled.current.channels.add(channel);
    if (viewMode === "focus" ? channel === selectedChannel : NUSCENES_CAMERAS.every(camera => settled.current.channels.has(camera.channel))) onFrameReady?.(token);
  }, [sampleToken, viewMode, selectedChannel, onFrameReady]);

  const frontCameras = NUSCENES_CAMERAS.slice(0, 3);
  const backCameras = NUSCENES_CAMERAS.slice(3, 6);
  const activeCamera = NUSCENES_CAMERAS.find((c) => c.channel === selectedChannel) || NUSCENES_CAMERAS[1];

  return (
    <section ref={ref} aria-label="Camera quanh xe" className={`flex flex-col gap-5 border-t border-[var(--line)] pt-7 text-[var(--foreground)] ${className}`}>
      {/* Top Header & Controls */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-[var(--accent-strong)]">04 / Quan sát nhiều hướng</p>
          <h2 className="mt-1 text-lg font-semibold tracking-[-0.025em]">Camera quanh xe <span className="ml-1 align-middle text-xs font-medium text-[var(--muted)]">6 góc nhìn</span></h2>
          <p className="mt-1 text-xs text-[var(--muted)]">Ảnh đã qua bộ lọc riêng tư · Đồng bộ với frame <span className="font-mono text-[var(--foreground)]">{sampleToken ? sampleToken.slice(0, 8) : "—"}</span></p>
        </div>

        {/* View toggles & refresh */}
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-[var(--line)] bg-white p-0.5 text-xs">
            <button
              type="button"
              aria-pressed={viewMode === "grid"}
              onClick={() => setViewMode("grid")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                viewMode === "grid"
                  ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                  : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Lưới 6 Camera
            </button>
            <button
              type="button"
              aria-pressed={viewMode === "focus"}
              onClick={() => setViewMode("focus")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                viewMode === "focus"
                  ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                  : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Xem một camera
            </button>
          </div>

          <button
            type="button"
            onClick={() => setRefreshSeed((s) => s + 1)}
            aria-label="Tải lại toàn bộ cụm camera"
            title="Tải lại toàn bộ cụm camera"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-[var(--line)] bg-white text-[var(--muted)] transition-colors hover:text-[var(--foreground)]"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* Main View Area */}
      {!near ? <div className="grid min-h-28 place-items-center rounded-xl bg-[var(--surface-subtle)] text-xs text-[var(--muted)]">Camera sẽ tải khi bạn cuộn tới khu vực này.</div> : viewMode === "grid" ? (
        <div className="flex flex-col gap-4">
          {/* Front Cameras Group */}
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)] mb-2 flex items-center gap-1.5">
              <span>▲ Cụm Phía Trước (Front Arc)</span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {frontCameras.map((cam) => (
                <CameraCard
                  key={`${cam.channel}-${sampleToken}-${refreshSeed}`}
                  sampleToken={sampleToken}
                  channel={cam.channel}
                  label={cam.label}
                  onFrameSettled={onFrameSettled}
                  isFocused={selectedChannel === cam.channel}
                  onFocus={() => { setSelectedChannel(cam.channel); setViewMode("focus"); }}
                />
              ))}
            </div>
          </div>

          {/* Back Cameras Group */}
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)] mb-2 flex items-center gap-1.5">
              <span>▼ Cụm Phía Sau (Rear Arc)</span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {backCameras.map((cam) => (
                <CameraCard
                  key={`${cam.channel}-${sampleToken}-${refreshSeed}`}
                  sampleToken={sampleToken}
                  channel={cam.channel}
                  label={cam.label}
                  onFrameSettled={onFrameSettled}
                  isFocused={selectedChannel === cam.channel}
                  onFocus={() => { setSelectedChannel(cam.channel); setViewMode("focus"); }}
                />
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Focus Single View */
        <div className="flex flex-col gap-3">
          {/* Channel selector tabs */}
          <div className="flex flex-wrap gap-1.5 border-b border-[var(--line)] pb-2">
            {NUSCENES_CAMERAS.map((cam) => (
              <button
                type="button"
                aria-pressed={selectedChannel === cam.channel}
                key={cam.channel}
                onClick={() => setSelectedChannel(cam.channel)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                  selectedChannel === cam.channel
                    ? "bg-[var(--accent)] text-white"
                    : "bg-white text-[var(--muted)] hover:text-[var(--foreground)] border border-[var(--line)]"
                }`}
              >
                {cam.label}
              </button>
            ))}
          </div>

          <div className="max-w-4xl mx-auto w-full">
            <CameraCard
              key={`${activeCamera.channel}-${sampleToken}-${refreshSeed}`}
              sampleToken={sampleToken}
              channel={activeCamera.channel}
              label={activeCamera.label}
              onFrameSettled={onFrameSettled}
              isFocused={true}
            />
          </div>
        </div>
      )}

      {/* Security notice footer */}
      <div className="flex items-center justify-between gap-2 border-t border-[var(--line)] pt-4 text-xs leading-5 text-[var(--muted)]">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-[var(--accent-strong)] flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span>
            Ảnh được xử lý bằng bộ lọc khuôn mặt và biển số trước khi hiển thị. Bộ lọc tự động có thể bỏ sót; cần kiểm tra ảnh trước khi chia sẻ.
          </span>
        </div>
      </div>
    </section>
  );
}
