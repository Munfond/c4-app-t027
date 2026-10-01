type LoadingProps = {
  className?: string;
  label?: string;
};

export function LoadingSpinner({
  className = "size-5",
  label,
}: LoadingProps) {
  return (
    <span className="inline-flex items-center gap-2" role={label ? "status" : undefined}>
      <span
        aria-hidden="true"
        className={[
          "animate-spin rounded-full border-2 border-current border-r-transparent",
          className,
        ].join(" ")}
      />
      {label ? <span className="text-sm font-medium">{label}</span> : null}
    </span>
  );
}

export function PageLoading() {
  return (
    <div aria-label="Đang tải nội dung" className="grid gap-5" role="status">
      <div className="grid gap-2">
        <div className="skeleton h-7 w-52 rounded-lg" />
        <div className="skeleton h-4 w-80 max-w-full rounded-md" />
      </div>
      <div className="skeleton h-20 rounded-[var(--radius)]" />
      <div className="grid min-h-96 gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="skeleton rounded-[var(--radius)]" />
        <div className="skeleton rounded-[var(--radius)]" />
      </div>
      <span className="sr-only">Đang tải…</span>
    </div>
  );
}
