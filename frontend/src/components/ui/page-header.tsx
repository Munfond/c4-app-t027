import type { ReactNode } from "react";

type PageHeaderProps = {
  actions?: ReactNode;
  description: string;
  eyebrow?: string;
  title: string;
};

export function PageHeader({
  actions,
  description,
  eyebrow = "ADAS Perception",
  title,
}: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="max-w-3xl">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[var(--accent-strong)]">
          {eyebrow}
        </p>
        <h1 className="text-2xl font-bold tracking-[-0.025em] text-[var(--foreground)] md:text-[28px]">
          {title}
        </h1>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{description}</p>
      </div>
      {actions ? <div className="flex shrink-0 gap-2">{actions}</div> : null}
    </div>
  );
}
