"use client";

import type { BevLayerVisibility } from "@/lib/viewer";

export interface BevLayerControlsProps {
  value: BevLayerVisibility;
  onChange: (value: BevLayerVisibility) => void;
  disabled?: boolean;
}

const LAYER_OPTIONS = [
  { key: "detections", label: "Detection boxes" },
  { key: "confidence", label: "Class và confidence" },
  { key: "grid", label: "Lưới 10 m" },
  { key: "egoMarker", label: "Ego và hướng tiến" },
] as const satisfies readonly {
  key: keyof BevLayerVisibility;
  label: string;
}[];

export function BevLayerControls({
  value,
  onChange,
  disabled = false,
}: BevLayerControlsProps) {
  return (
    <fieldset
      className="absolute bottom-3 right-3 rounded-lg border border-zinc-700/80 bg-zinc-950/85 px-3 py-2 shadow-lg backdrop-blur"
      disabled={disabled}
    >
      <legend className="sr-only">Các lớp hiển thị trong BEV</legend>
      <p
        aria-hidden="true"
        className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400"
      >
        Layers
      </p>
      <div className="grid gap-1.5">
        {LAYER_OPTIONS.map((option) => {
          const confidenceUnavailable =
            option.key === "confidence" && !value.detections;

          return (
            <label
              key={option.key}
              className={`flex items-center gap-2 text-xs ${
                disabled || confidenceUnavailable
                  ? "cursor-not-allowed text-zinc-600"
                  : "cursor-pointer text-zinc-200"
              }`}
            >
              <input
                checked={value[option.key]}
                className="h-3.5 w-3.5 accent-cyan-500"
                disabled={disabled || confidenceUnavailable}
                onChange={(event) =>
                  onChange({
                    ...value,
                    [option.key]: event.currentTarget.checked,
                  })
                }
                type="checkbox"
              />
              <span>{option.label}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
