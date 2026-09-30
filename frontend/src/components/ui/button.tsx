import type { ButtonHTMLAttributes, ReactNode } from "react";
import { LoadingSpinner } from "./loading";

type ButtonVariant = "primary" | "secondary" | "ghost";
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  loading?: boolean;
  variant?: ButtonVariant;
};

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--accent)] text-white shadow-sm hover:bg-[var(--accent-strong)]",
  secondary:
    "border border-[var(--line)] bg-white text-[var(--foreground)] hover:bg-[var(--surface-subtle)]",
  ghost:
    "text-[var(--muted)] hover:bg-[var(--surface-subtle)] hover:text-[var(--foreground)]",
};

export function Button({
  children,
  className = "",
  disabled,
  loading = false,
  type = "button",
  variant = "primary",
  ...props
}: ButtonProps) {
  return (
    <button
      className={[
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-[10px] px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className,
      ].join(" ")}
      disabled={disabled || loading}
      type={type}
      {...props}
    >
      {loading ? <LoadingSpinner className="size-4" /> : null}
      {children}
    </button>
  );
}
