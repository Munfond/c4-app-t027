import { getClassColor, type ClassColorMap } from "@/lib/viewer";

export interface BevLegendProps {
  classNames: readonly string[];
  classColors?: ClassColorMap;
}

export function BevLegend({ classNames, classColors }: BevLegendProps) {
  if (classNames.length === 0) {
    return null;
  }

  return (
    <div
      aria-label="Chú giải lớp detection"
      className="pointer-events-none absolute bottom-3 left-3 max-w-[calc(100%-1.5rem)] rounded-lg border border-zinc-700/80 bg-zinc-950/85 px-3 py-2 shadow-lg backdrop-blur"
    >
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
        Detection classes
      </p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1.5">
        {classNames.map((className) => (
          <li
            key={className}
            className="flex items-center gap-1.5 text-xs text-zinc-200"
          >
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: getClassColor(className, classColors) }}
            />
            <span>{className}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
