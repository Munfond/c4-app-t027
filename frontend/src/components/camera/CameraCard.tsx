"use client";

import React, { useState } from "react";

export interface CameraCardProps {
  sampleToken: string;
  channel: string;
  label: string;
  isFocused?: boolean;
  onFocus?: () => void;
}

export function CameraCard({
  sampleToken,
  channel,
  label,
  isFocused = false,
  onFocus,
}: CameraCardProps) {
  const [loading, setLoading] = useState(true);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  const imageUrl = sampleToken
    ? `/api/v1/lab/frames/${sampleToken}/cameras/${channel}?retry=${retryKey}`
    : "";

  const handleRetry = (e: React.MouseEvent) => {
    e.stopPropagation();
    setLoading(true);
    setErrorStatus(null);
    setRetryKey((k) => k + 1);
  };

  return (
    <div
      onClick={onFocus}
      className={`group relative flex flex-col overflow-hidden rounded-xl border transition-all duration-200 cursor-pointer ${
        isFocused
          ? "border-blue-500 bg-zinc-900/90 shadow-lg shadow-blue-500/10 ring-2 ring-blue-500/30"
          : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/40"
      }`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-zinc-800/80 bg-zinc-900/80 px-3 py-2 text-xs backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-500/80 animate-pulse" />
          <span className="font-semibold text-zinc-200">{label}</span>
          <span className="font-mono text-[10px] text-zinc-500">{channel}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {errorStatus === 503 ? (
            <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400 border border-amber-500/20">
              Fail-Closed
            </span>
          ) : (
            <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400 border border-emerald-500/20">
              Anonymized
            </span>
          )}
        </div>
      </div>

      {/* Media area */}
      <div className="relative aspect-[16/9] w-full overflow-hidden bg-zinc-900/90 flex items-center justify-center">
        {loading && !errorStatus && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-zinc-900">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <span className="text-[11px] text-zinc-400">Đang tải & xác thực ảnh...</span>
          </div>
        )}

        {errorStatus ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center bg-zinc-950/90">
            {errorStatus === 503 ? (
              <>
                <svg
                  className="h-8 w-8 text-amber-400 mb-2"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <div className="text-xs font-medium text-zinc-200 mb-1">
                  Bảo vệ Fail-Closed (503)
                </div>
                <p className="text-[11px] text-zinc-400 max-w-[220px] mb-3">
                  Ảnh chưa qua bộ lọc làm mờ khuôn mặt / biển số xe. Hệ thống chặn trả ảnh thô để bảo mật.
                </p>
              </>
            ) : (
              <>
                <svg
                  className="h-8 w-8 text-rose-400 mb-2"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                  />
                </svg>
                <div className="text-xs font-medium text-zinc-200 mb-1">
                  Không thể nạp camera ({errorStatus})
                </div>
              </>
            )}
            <button
              onClick={handleRetry}
              className="rounded-md bg-zinc-800 hover:bg-zinc-700 px-2.5 py-1 text-[11px] font-medium text-zinc-200 transition-colors border border-zinc-700"
            >
              Thử lại
            </button>
          </div>
        ) : (
          sampleToken && (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={imageUrl}
              alt={`${label} (${channel})`}
              className={`h-full w-full object-cover transition-opacity duration-300 ${
                loading ? "opacity-0" : "opacity-100"
              }`}
              onLoad={() => setLoading(false)}
              onError={(e) => {
                setLoading(false);
                const target = e.currentTarget;
                // If failed, probe status via fetch
                fetch(target.src)
                  .then((res) => setErrorStatus(res.status))
                  .catch(() => setErrorStatus(500));
              }}
            />
          )
        )}
      </div>
    </div>
  );
}
