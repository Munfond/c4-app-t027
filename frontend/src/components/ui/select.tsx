import type { SelectHTMLAttributes } from "react";
import { ChevronDownIcon } from "./icons";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
};

export function Select({ className = "", label, id, ...props }: SelectProps) {
  const selectId = id ?? label.toLowerCase().replaceAll(" ", "-");

  return (
    <label className={["grid min-w-0 gap-2", className].join(" ")} htmlFor={selectId}>
      <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--muted)]">
        {label}
      </span>
      <span className="relative block">
        <select
          className="h-11 w-full appearance-none rounded-lg border border-[var(--line)] bg-white py-0 pl-3 pr-9 text-[13px] font-medium text-[var(--foreground)] outline-none transition-colors hover:border-[#adbfbb] focus:border-[var(--accent)] focus:ring-3 focus:ring-[#087d7422] disabled:cursor-not-allowed disabled:bg-[var(--surface-subtle)] disabled:text-[var(--muted)]"
          id={selectId}
          {...props}
        />
        <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" />
      </span>
    </label>
  );
}
