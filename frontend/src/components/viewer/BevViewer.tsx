"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  areBevViewStatesEquivalent,
  DEFAULT_BEV_LAYERS,
  DEFAULT_BEV_VIEW_STATE,
  type BevLayerVisibility,
  type BevViewportMetrics,
  type BevViewState,
  type ViewerDetectionFrame,
} from "@/lib/viewer";
import { loadEnvironmentFrame } from "@/lib/lab-frame-cache";
import { BevRenderer } from "@/lib/viewer/bev-renderer";

import { BevLayerControls } from "./BevLayerControls";
import { BevLegend } from "./BevLegend";
import { centreDistance } from "@/lib/viewer/proximity";

export interface BevViewerProps {
  frame: ViewerDetectionFrame | null;
  isLoading?: boolean;
  error?: string | null;
  layers?: BevLayerVisibility;
  onLayersChange?: (layers: BevLayerVisibility) => void;
  viewState?: BevViewState;
  onViewStateChange?: (viewState: BevViewState) => void;
  showLegend?: boolean;
  showLayerControls?: boolean;
  showMetadata?: boolean;
  showViewControls?: boolean;
  className?: string;
  ariaLabel?: string;
}

export function BevViewer({
  frame,
  isLoading = false,
  error = null,
  layers: controlledLayers,
  onLayersChange,
  viewState,
  onViewStateChange,
  showLegend = true,
  showLayerControls = true,
  showMetadata = true,
  showViewControls = true,
  className = "",
  ariaLabel = "Bird's-eye-view detection viewer",
}: BevViewerProps) {
  const [localLayers, setLocalLayers] = useState<BevLayerVisibility>(DEFAULT_BEV_LAYERS);
  const layers = controlledLayers ?? localLayers;
  const changeLayers = onLayersChange ?? setLocalLayers;
  const [environmentStatus, setEnvironmentStatus] = useState<{token: string; message: string} | null>(null);
  const sampleToken = frame?.frame.sampleToken;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const nearest = useMemo(() => [...(frame?.detections ?? [])].sort((a, b) => centreDistance(a) - centreDistance(b)), [frame]);
  const selected = nearest.find(item => item.id === selectedId) ?? nearest[0];
  const detailRef = useRef<HTMLDetailsElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<BevRenderer | null>(null);
  const initialViewStateRef = useRef(viewState);
  const initialAriaLabelRef = useRef(ariaLabel);
  const onViewStateChangeRef = useRef(onViewStateChange);
  const [rendererError, setRendererError] = useState<string | null>(null);
  const [viewportMetrics, setViewportMetrics] =
    useState<BevViewportMetrics | null>(null);

  useEffect(() => {
    onViewStateChangeRef.current = onViewStateChange;
  }, [onViewStateChange]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    let isMounted = true;

    try {
      const renderer = new BevRenderer(container, {
        ariaLabel: initialAriaLabelRef.current,
        onSelectDetection: id => { setSelectedId(id); if (detailRef.current) detailRef.current.open = true; },
        initialViewState: initialViewStateRef.current,
        onViewStateChange: (nextViewState) => {
          onViewStateChangeRef.current?.(nextViewState);
        },
        onViewportMetricsChange: (nextMetrics) => {
          setViewportMetrics((currentMetrics) => {
            if (
              currentMetrics &&
              Math.abs(
                currentMetrics.visibleWidthMeters -
                  nextMetrics.visibleWidthMeters,
              ) < 0.01 &&
              Math.abs(
                currentMetrics.visibleHeightMeters -
                  nextMetrics.visibleHeightMeters,
              ) < 0.01
            ) {
              return currentMetrics;
            }

            return nextMetrics;
          });
        },
      });
      rendererRef.current = renderer;
    } catch (cause) {
      const message =
        cause instanceof Error
          ? cause.message
          : "Không thể khởi tạo WebGL renderer.";
      queueMicrotask(() => {
        if (isMounted) {
          setRendererError(message);
        }
      });
    }

    return () => {
      isMounted = false;
      rendererRef.current?.dispose();
      rendererRef.current = null;
    };
  }, []);

  useEffect(() => {
    rendererRef.current?.setAriaLabel(ariaLabel);
  }, [ariaLabel]);

  useEffect(() => {
    rendererRef.current?.setDetections(frame?.detections ?? []);
  }, [frame]);

  useEffect(() => {
    rendererRef.current?.setSelectedDetection(selected?.id ?? null);
  }, [selected, frame]);

  useEffect(() => {
    rendererRef.current?.setLayers(layers);
  }, [layers]);

  useEffect(() => {
    if (viewState) {
      rendererRef.current?.setViewState(viewState);
    }
  }, [viewState]);

  useEffect(() => {
    let active = true;
    rendererRef.current?.setEnvironment([]);
    if (!sampleToken) return () => { active = false; };
    void loadEnvironmentFrame(sampleToken).then(data => {
        if (!active) return;
        rendererRef.current?.setEnvironment(data.points);
        setEnvironmentStatus({ token: sampleToken, message: `${data.points.length.toLocaleString()} điểm LiDAR · bán kính 65 m` });
      }).catch(reason => {
        if (active) setEnvironmentStatus({ token: sampleToken, message: reason instanceof Error ? reason.message : "Chưa có nền LiDAR cho frame này" });
      });
    return () => { active = false; };
  }, [sampleToken]);

  const statusMessage = rendererError ?? error;
  const isEmpty = !isLoading && !statusMessage && frame?.detections.length === 0;
  const resetDisabled = viewState !== undefined && !onViewStateChange;

  const handleResetView = () => {
    const renderer = rendererRef.current;
    const rendererViewState = renderer?.getViewState();
    const controlledViewIsDefault =
      !viewState ||
      areBevViewStatesEquivalent(viewState, DEFAULT_BEV_VIEW_STATE);
    const rendererViewIsDefault =
      !rendererViewState ||
      areBevViewStatesEquivalent(rendererViewState, DEFAULT_BEV_VIEW_STATE);
    if (controlledViewIsDefault && rendererViewIsDefault) {
      if (renderer) {
        setViewportMetrics(renderer.getViewportMetrics());
      }
      return;
    }

    const defaultViewState: BevViewState = {
      center: { ...DEFAULT_BEV_VIEW_STATE.center },
      visibleHeightMeters: DEFAULT_BEV_VIEW_STATE.visibleHeightMeters,
    };
    renderer?.setViewState(defaultViewState);
    if (renderer) {
      setViewportMetrics(renderer.getViewportMetrics());
    }
    onViewStateChange?.(defaultViewState);
  };

  return (
    <section
      aria-busy={isLoading}
      className={`relative h-full w-full min-h-0 overflow-hidden bg-[#08171b] ${className}`}
    >
      <div ref={containerRef} className="absolute inset-0" />

      {frame && (
        <div className="bev-readout">
          {showMetadata && <p className="bev-readout-title">BEV / MẶT BẰNG</p>}
          <p className="mt-1 text-xs text-[#d3dfda]">
            {frame.detections.length} vật cản · Tính sẵn
          </p>
          <p className="mt-1 max-w-52 text-[10px] text-[#91a9aa]">{environmentStatus && environmentStatus.token === sampleToken ? environmentStatus.message : "Đang tải nền LiDAR…"}</p>
        </div>
      )}

      {showViewControls && (
        <div className="bev-view-controls">
          <p className="text-right text-[10px] text-[#91a9aa]">
            {viewportMetrics
              ? `Ngang ${Math.round(viewportMetrics.visibleWidthMeters)} m · Dọc ${Math.round(viewportMetrics.visibleHeightMeters)} m · Lưới ${viewportMetrics.gridSpacingMeters} m`
              : "BEV hệ mét · Lưới 10 m"}
          </p>
          <button
            className="min-h-9 border-b border-[#d9ee9840] px-1 text-[11px] text-[#d9ee98] transition-colors hover:border-[#d9ee98] disabled:cursor-not-allowed disabled:text-zinc-600"
            disabled={resetDisabled}
            onClick={handleResetView}
            title={
              resetDisabled
                ? "Cần onViewStateChange khi viewState được điều khiển từ parent"
                : "Đặt lại pan và zoom"
            }
            type="button"
          >
            Đặt lại góc nhìn
          </button>
        </div>
      )}

      {showLegend && frame && !isLoading && !statusMessage && (
        <BevLegend />
      )}

      {showLayerControls && (!controlledLayers || onLayersChange) && !isLoading && !statusMessage && (
        <BevLayerControls value={layers} onChange={changeLayers} />
      )}

      {selected && !isLoading && !statusMessage && showMetadata && (
        <details ref={detailRef} className="absolute left-3 top-28 max-w-[46%] rounded-md border border-white/15 bg-[#071720]/95 p-2.5 text-[11px] text-slate-200">
          <summary className="cursor-pointer text-teal-200">Vật cản đang chọn · {centreDistance(selected).toFixed(1)} m</summary>
          <label className="mt-2 block text-teal-200" htmlFor={`obstacle-${frame?.modelId}`}>Vật cản · viền trắng khi chọn</label>
          <select id={`obstacle-${frame?.modelId}`} value={selected.id} onChange={e => setSelectedId(e.target.value)} className="my-1 w-full rounded bg-[#183b45] p-1 text-xs">
            {nearest.map((item, index) => <option key={item.id} value={item.id}>#{index + 1} · {centreDistance(item).toFixed(1)} m</option>)}
          </select>
          <p>Dài × rộng × cao</p>
          <p className="font-mono text-white">{selected.size.length.toFixed(1)} × {selected.size.width.toFixed(1)} × {selected.size.height.toFixed(1)} m</p>
          <p className="mt-1">{selected.center.forward >= 0 ? "Trước" : "Sau"} {Math.abs(selected.center.forward).toFixed(1)} m · {selected.center.left >= 0 ? "Trái" : "Phải"} {Math.abs(selected.center.left).toFixed(1)} m</p>
          <p className="mt-1 max-w-44 text-[10px] text-slate-400">Khoảng cách đến tâm hộp, không phải khoảng hở an toàn.</p>
        </details>
      )}

      {isLoading && (
        <div className="absolute inset-0 grid place-items-center bg-[#071720]/85 text-sm text-zinc-300">
          Đang tải vật cản…
        </div>
      )}

      {statusMessage && !isLoading && (
        <div
          role="alert"
          className="absolute inset-0 grid place-items-center bg-[#071720]/90 p-6 text-center text-sm text-rose-300"
        >
          {statusMessage}
        </div>
      )}

      {isEmpty && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center p-6 text-center text-sm text-zinc-400">
          Không có hộp vật cản vượt ngưỡng; nền LiDAR vẫn là quan sát thực.
        </div>
      )}
    </section>
  );
}
