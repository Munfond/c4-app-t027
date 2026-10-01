"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  areBevViewStatesEquivalent,
  DEFAULT_BEV_LAYERS,
  DEFAULT_BEV_VIEW_STATE,
  type BevLayerVisibility,
  type BevViewportMetrics,
  type BevViewState,
  type ClassColorMap,
  type ViewerDetectionFrame,
} from "@/lib/viewer";
import { BevRenderer } from "@/lib/viewer/bev-renderer";

import { BevLayerControls } from "./BevLayerControls";
import { BevLegend } from "./BevLegend";

export interface BevViewerProps {
  frame: ViewerDetectionFrame | null;
  isLoading?: boolean;
  error?: string | null;
  layers?: BevLayerVisibility;
  onLayersChange?: (layers: BevLayerVisibility) => void;
  viewState?: BevViewState;
  onViewStateChange?: (viewState: BevViewState) => void;
  classColors?: ClassColorMap;
  legendClassNames?: readonly string[];
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
  layers = DEFAULT_BEV_LAYERS,
  onLayersChange,
  viewState,
  onViewStateChange,
  classColors,
  legendClassNames,
  showLegend = true,
  showLayerControls = true,
  showMetadata = true,
  showViewControls = true,
  className = "",
  ariaLabel = "Bird's-eye-view detection viewer",
}: BevViewerProps) {
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
    rendererRef.current?.setDetections(frame?.detections ?? [], classColors);
  }, [classColors, frame]);

  useEffect(() => {
    rendererRef.current?.setLayers(layers);
  }, [layers]);

  useEffect(() => {
    if (viewState) {
      rendererRef.current?.setViewState(viewState);
    }
  }, [viewState]);

  const detectedClassNames = useMemo(
    () =>
      [...new Set(frame?.detections.map((detection) => detection.className) ?? [])]
        .sort((first, second) => first.localeCompare(second)),
    [frame],
  );
  const classNames = legendClassNames ?? detectedClassNames;

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
      className={`relative h-full w-full min-h-0 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 ${className}`}
    >
      <div ref={containerRef} className="absolute inset-0" />

      {showMetadata && frame && (
        <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-zinc-700/80 bg-zinc-950/85 px-3 py-2 text-xs shadow-lg backdrop-blur">
          <p className="font-medium text-zinc-100">{frame.modelId}</p>
          <p className="mt-0.5 text-zinc-400">
            {frame.detections.length} boxes · Tính sẵn
          </p>
        </div>
      )}

      {showViewControls && (
        <div className="absolute right-3 top-3 flex max-w-[55%] flex-col items-end gap-2">
          <p className="rounded-md border border-zinc-800 bg-zinc-950/80 px-2 py-1 text-right text-[11px] text-zinc-400 backdrop-blur">
            {viewportMetrics
              ? `Ngang ${Math.round(viewportMetrics.visibleWidthMeters)} m · Dọc ${Math.round(viewportMetrics.visibleHeightMeters)} m · Lưới ${viewportMetrics.gridSpacingMeters} m`
              : "BEV hệ mét · Lưới 10 m"}
          </p>
          <button
            className="rounded-md border border-zinc-700 bg-zinc-900/90 px-2.5 py-1.5 text-xs font-medium text-zinc-200 shadow transition-colors hover:border-zinc-500 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:text-zinc-600"
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
        <BevLegend classNames={classNames} classColors={classColors} />
      )}

      {showLayerControls && onLayersChange && !isLoading && !statusMessage && (
        <BevLayerControls value={layers} onChange={onLayersChange} />
      )}

      {isLoading && (
        <div className="absolute inset-0 grid place-items-center bg-zinc-950/70 text-sm text-zinc-300 backdrop-blur-sm">
          Đang tải detection…
        </div>
      )}

      {statusMessage && !isLoading && (
        <div
          role="alert"
          className="absolute inset-0 grid place-items-center bg-zinc-950/80 p-6 text-center text-sm text-rose-300 backdrop-blur-sm"
        >
          {statusMessage}
        </div>
      )}

      {isEmpty && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center p-6 text-center text-sm text-zinc-400">
          Frame hợp lệ, không có detection vượt ngưỡng đã chọn.
        </div>
      )}
    </section>
  );
}
