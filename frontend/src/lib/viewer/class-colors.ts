export type ClassColorMap = Readonly<Record<string, string>>;

const CLASS_COLOR_PALETTE = [
  "#38bdf8",
  "#f97316",
  "#a78bfa",
  "#34d399",
  "#fb7185",
  "#facc15",
  "#22d3ee",
  "#e879f9",
] as const;

function hashClassName(className: string): number {
  let hash = 2166136261;

  for (const character of className.trim().toLowerCase()) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }

  return hash >>> 0;
}

/** Returns the same color for a class in Lab and Compare without fixed labels. */
export function getClassColor(
  className: string,
  overrides?: ClassColorMap,
): string {
  const override = overrides?.[className];
  if (override) {
    return override;
  }

  return CLASS_COLOR_PALETTE[
    hashClassName(className) % CLASS_COLOR_PALETTE.length
  ];
}
