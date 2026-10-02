"use client";

import React, { useState } from "react";
import { CameraCard } from "./CameraCard";

export interface CameraPanelProps {
  sampleToken: string;
  className?: string;
}

export const NUSCENES_CAMERAS = [
  { channel: "CAM_FRONT_LEFT", label: "Front Left", pos: "front-left" },
  { channel: "CAM_FRONT", label: "Front Center", pos: "front" },
  { channel: "CAM_FRONT_RIGHT", label: "Front Right", pos: "front-right" },
  { channel: "CAM_BACK_LEFT", label: "Back Left", pos: "back-left" },
  { channel: "CAM_BACK", label: "Back Center", pos: "back" },
  { channel: "CAM_BACK_RIGHT", label: "Back Right", pos: "back-right" },
] as const;

export function CameraPanel({ sampleToken, className = "" }: CameraPanelProps) {
  const [viewMode, setViewMode] = useState<"grid" | "focus">("grid");
  const [selectedChannel, setSelectedChannel] = useState<string>("CAM_FRONT");
  const [refreshSeed, setRefreshSeed] = useState(0);

  const frontCameras = NUSCENES_CAMERAS.slice(0, 3);
  const backCameras = NUSCENES_CAMERAS.slice(3, 6);
  const activeCamera = NUSCENES_CAMERAS.find((c) => c.channel === selectedChannel) || NUSCENES_CAMERAS[1];

  return (
    <div className={`flex flex-col gap-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-[var(--foreground)] ${className}`}>
      {/* Top Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] pb-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent-strong)] border border-[var(--line)]">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-[var(--foreground)] flex items-center gap-2">
              Cụm 6 Camera Đa hướng (Multi-Camera Surround)
              <span className="rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--accent-strong)] border border-[var(--line)]">
                Ảnh qua bộ lọc
              </span>
            </h2>
            <p className="text-xs text-[var(--muted)]">
              Đồng bộ theo Frame: <span className="font-mono text-[var(--foreground)]">{sampleToken ? sampleToken.slice(0, 16) + "..." : "Chưa chọn frame"}</span>
            </p>
          </div>
        </div>

        {/* View toggles & refresh */}
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-[var(--surface-subtle)] p-0.5 border border-[var(--line)] text-xs">
            <button
              onClick={() => setViewMode("grid")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                viewMode === "grid"
                  ? "bg-[var(--surface-subtle)] text-[var(--foreground)] shadow-sm"
                  : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Lưới 6 Camera
            </button>
            <button
              onClick={() => setViewMode("focus")}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                viewMode === "focus"
                  ? "bg-[var(--surface-subtle)] text-[var(--foreground)] shadow-sm"
                  : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Xem một camera
            </button>
          </div>

          <button
            onClick={() => setRefreshSeed((s) => s + 1)}
            title="Tải lại toàn bộ cụm camera"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface-subtle)] text-[var(--muted)] hover:border-[var(--line)] hover:text-[var(--foreground)] transition-colors"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* Main View Area */}
      {viewMode === "grid" ? (
        <div className="flex flex-col gap-4">
          {/* Front Cameras Group */}
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)] mb-2 flex items-center gap-1.5">
              <span>▲ Cụm Phía Trước (Front Arc)</span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {frontCameras.map((cam) => (
                <CameraCard
                  key={`${cam.channel}-${sampleToken}-${refreshSeed}`}
                  sampleToken={sampleToken}
                  channel={cam.channel}
                  label={cam.label}
                  isFocused={selectedChannel === cam.channel}
                  onFocus={() => setSelectedChannel(cam.channel)}
                />
              ))}
            </div>
          </div>

          {/* Back Cameras Group */}
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)] mb-2 flex items-center gap-1.5">
              <span>▼ Cụm Phía Sau (Rear Arc)</span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {backCameras.map((cam) => (
                <CameraCard
                  key={`${cam.channel}-${sampleToken}-${refreshSeed}`}
                  sampleToken={sampleToken}
                  channel={cam.channel}
                  label={cam.label}
                  isFocused={selectedChannel === cam.channel}
                  onFocus={() => setSelectedChannel(cam.channel)}
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
                key={cam.channel}
                onClick={() => setSelectedChannel(cam.channel)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                  selectedChannel === cam.channel
                    ? "bg-[var(--accent-strong)] text-white shadow-md shadow-[var(--shadow)]"
                    : "bg-[var(--surface-subtle)] text-[var(--muted)] hover:bg-[var(--surface-subtle)] hover:text-[var(--foreground)] border border-[var(--line)]"
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
              isFocused={true}
            />
          </div>
        </div>
      )}

      {/* Security notice footer */}
      <div className="flex items-center justify-between gap-2 rounded-xl bg-[var(--surface-subtle)] border border-[var(--line)] px-3 py-2 text-[11px] text-[var(--muted)]">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-[var(--accent-strong)] flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span>
            Ảnh được xử lý bằng bộ lọc khuôn mặt và biển số trước khi hiển thị. Bộ lọc tự động có thể bỏ sót; cần kiểm tra ảnh trước khi chia sẻ.
          </span>
        </div>
      </div>
    </div>
  );
}
