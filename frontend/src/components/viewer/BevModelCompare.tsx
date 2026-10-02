"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  areBevViewStatesEquivalent,
  constrainBevViewState,
  DEFAULT_BEV_LAYERS,
  DEFAULT_BEV_VIEW_STATE,
  type BevLayerVisibility,
  type BevViewState,
  type ViewerDetectionFrame,
} from "@/lib/viewer";

import { BevViewer } from "./BevViewer";

export interface BevComparePane {
  /** Model selected by the parent. Used to reject stale responses. */
  modelId: string;
  /** Human-readable label supplied by the model registry, when available. */
  modelLabel?: string;
  frame: ViewerDetectionFrame | null;
  isLoading?: boolean;
  error?: string | null;
}

export interface BevModelCompareProps {
  /** The single parent-owned frame selection shared by both panes. */
  sampleToken: string;
  /** The single API threshold used to request both model results. */
  threshold: number;
  modelA: BevComparePane;
  modelB: BevComparePane;
  layers?: BevLayerVisibility;
  onLayersChange?: (layers: BevLayerVisibility) => void;
  viewState?: BevViewState;
  onViewStateChange?: (viewState: BevViewState) => void;
  className?: string;
}

function copyDefaultViewState(): BevViewState {
  return {
    center: { ...DEFAULT_BEV_VIEW_STATE.center },
    visibleHeightMeters: DEFAULT_BEV_VIEW_STATE.visibleHeightMeters,
  };
}

function getPaneDataError(
  pane: BevComparePane,
  sampleToken: string,
): string | null {
  if (!pane.frame) {
    return null;
  }

  if (pane.frame.frame.sampleToken !== sampleToken) {
    return `Đã chặn kết quả sai frame: cần ${sampleToken}, nhận ${pane.frame.frame.sampleToken}.`;
  }

  if (pane.frame.modelId !== pane.modelId) {
    return `Đã chặn kết quả sai model: cần ${pane.modelId}, nhận ${pane.frame.modelId}.`;
  }

  return null;
}

function getPaneStatus(
  pane: BevComparePane,
  dataError: string | null,
): string {
  if (pane.isLoading) {
    return "Đang tải";
  }
  if (dataError || pane.error) {
    return "Có lỗi";
  }
  if (!pane.frame) {
    return "Chưa có dữ liệu";
  }

  return `${pane.frame.detections.length} vật cản · Tính sẵn`;
}

interface ComparePaneViewProps {
  heading: string;
  pane: BevComparePane;
  frame: ViewerDetectionFrame | null;
  dataError: string | null;
  layers: BevLayerVisibility;
  showLayerControls: boolean;
  onLayersChange?: (layers: BevLayerVisibility) => void;
  viewState: BevViewState;
  onViewStateChange: (viewState: BevViewState) => void;
}

function ComparePaneView({
  heading,
  pane,
  frame,
  dataError,
  layers,
  showLayerControls,
  onLayersChange,
  viewState,
  onViewStateChange,
}: ComparePaneViewProps) {
  return (
    <article className="flex min-h-[440px] min-w-0 flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950">
      <header className="flex min-h-14 items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            {heading}
          </p>
          <p
            className="truncate text-sm font-semibold text-zinc-100"
            title={pane.modelLabel ?? pane.modelId}
          >
            {pane.modelLabel || pane.modelId || "—"}
          </p>
        </div>
        <p className="shrink-0 text-right text-xs text-zinc-400">
          {getPaneStatus(pane, dataError)}
        </p>
      </header>

      <div className="min-h-0 flex-1">
        <BevViewer
          ariaLabel={`${heading}: ${pane.modelLabel ?? pane.modelId}`}
          error={dataError ?? pane.error}
          frame={frame}
          isLoading={pane.isLoading}
          layers={layers}
          onLayersChange={onLayersChange}
          onViewStateChange={onViewStateChange}
          showLayerControls={showLayerControls}
          showMetadata={false}
          viewState={viewState}
        />
      </div>
    </article>
  );
}

export function BevModelCompare({
  sampleToken,
  threshold,
  modelA,
  modelB,
  layers = DEFAULT_BEV_LAYERS,
  onLayersChange,
  viewState,
  onViewStateChange,
  className = "",
}: BevModelCompareProps) {
  const [uncontrolledViewState, setUncontrolledViewState] =
    useState<BevViewState>(copyDefaultViewState);
  const effectiveViewState = useMemo(
    () => constrainBevViewState(viewState ?? uncontrolledViewState),
    [uncontrolledViewState, viewState],
  );
  const effectiveViewStateRef = useRef(effectiveViewState);

  useEffect(() => {
    effectiveViewStateRef.current = effectiveViewState;
  }, [effectiveViewState]);

  const syncViewState = useCallback(
    (nextViewState: BevViewState) => {
      const constrainedViewState = constrainBevViewState(nextViewState);
      if (
        areBevViewStatesEquivalent(
          effectiveViewStateRef.current,
          constrainedViewState,
        )
      ) {
        return;
      }

      effectiveViewStateRef.current = constrainedViewState;

      // BevRenderer suppresses callbacks while applying this value to the
      // sibling pane, so only user-driven changes reach this callback.
      if (viewState === undefined) {
        setUncontrolledViewState(constrainedViewState);
      }
      onViewStateChange?.(constrainedViewState);
    },
    [onViewStateChange, viewState],
  );

  const modelADataError = getPaneDataError(modelA, sampleToken);
  const modelBDataError = getPaneDataError(modelB, sampleToken);
  const modelAFrame = modelADataError ? null : modelA.frame;
  const modelBFrame = modelBDataError ? null : modelB.frame;


  return (
    <section
      aria-label="So sánh BEV giữa hai mô hình"
      className={`flex h-full min-h-0 w-full flex-col gap-3 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-400">
        <p className="min-w-0 truncate" title={sampleToken}>
          Cùng frame: <span className="text-zinc-200">{sampleToken || "—"}</span>
        </p>
        <p>
          Ngưỡng API: <span className="text-zinc-200">{threshold}</span>
        </p>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-2">
        <ComparePaneView
          dataError={modelADataError}
          frame={modelAFrame}
          heading="Mô hình A"
          layers={layers}
          onLayersChange={onLayersChange}
          onViewStateChange={syncViewState}
          pane={modelA}
          showLayerControls={false}
          viewState={effectiveViewState}
        />
        <ComparePaneView
          dataError={modelBDataError}
          frame={modelBFrame}
          heading="Mô hình B"
          layers={layers}
          onLayersChange={onLayersChange}
          onViewStateChange={syncViewState}
          pane={modelB}
          showLayerControls
          viewState={effectiveViewState}
        />
      </div>
    </section>
  );
}
