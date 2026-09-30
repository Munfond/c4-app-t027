import type { SelectHTMLAttributes } from "react";
import { ChevronDownIcon } from "./icons";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
};

export function Select({ className = "", label, id, ...props }: SelectProps) {
  const selectId = id ?? label.toLowerCase().replaceAll(" ", "-");

  return (
    <label className={["grid gap-1.5", className].join(" ")} htmlFor={selectId}>
      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
        {label}
      </span>
      <span className="relative block">
        <select
          className="h-10 w-full appearance-none rounded-[10px] border border-[var(--line)] bg-white py-0 pl-3 pr-9 text-sm font-medium text-[var(--foreground)] shadow-sm outline-none transition hover:border-[#b8c8cb] focus:border-[var(--accent)] focus:ring-3 focus:ring-[#12a5941f] disabled:cursor-not-allowed disabled:bg-[var(--surface-subtle)] disabled:text-[var(--muted)]"
          id={selectId}
          {...props}
        />
        <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" />
      </span>
    </label>
  );
}
