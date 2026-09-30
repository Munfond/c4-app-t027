import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const baseProps = {
  "aria-hidden": true,
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 1.8,
  viewBox: "0 0 24 24",
};

export function LabIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M9 3h6M10 3v5.2l-5.1 8.5A2.8 2.8 0 0 0 7.3 21h9.4a2.8 2.8 0 0 0 2.4-4.3L14 8.2V3" />
      <path d="M7.2 15h9.6M9.2 12h5.6" />
    </svg>
  );
}

export function CompareIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <rect height="14" rx="2" width="7" x="3" y="5" />
      <rect height="14" rx="2" width="7" x="14" y="5" />
      <path d="M7 9h2M15 15h2" />
    </svg>
  );
}

export function BenchmarkIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
      <path d="m3 7 6-4 6 6 6-5" />
    </svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="m7 9 5 5 5-5" />
    </svg>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="m8 5 11 7-11 7V5Z" />
    </svg>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M12 3 13.8 8.2 19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" />
      <path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" />
    </svg>
  );
}
