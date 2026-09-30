"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  BenchmarkIcon,
  CompareIcon,
  LabIcon,
  SparkIcon,
} from "@/components/ui/icons";

const navigation = [
  { href: "/lab", icon: LabIcon, label: "Lab", shortLabel: "Lab" },
  {
    href: "/compare",
    icon: CompareIcon,
    label: "So sánh",
    shortLabel: "Compare",
  },
  {
    href: "/benchmarks",
    icon: BenchmarkIcon,
    label: "Đánh giá",
    shortLabel: "Benchmarks",
  },
];

function ProductMark() {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-10 place-items-center rounded-xl bg-[var(--accent)] text-white shadow-[0_7px_20px_rgb(18_165_148/25%)]">
        <SparkIcon className="size-5" />
      </span>
      <span>
        <span className="block text-sm font-bold tracking-[-0.02em] text-white">
          Perception Lab
        </span>
        <span className="mt-0.5 block text-[10px] font-semibold uppercase tracking-[0.17em] text-[#8fb0b8]">
          Team 27 · Munfond
        </span>
      </span>
    </div>
  );
}

function navLinkClasses(active: boolean, mobile: boolean) {
  if (mobile) {
    return [
      "flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl px-2 text-[11px] font-semibold transition",
      active
        ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
        : "text-[var(--muted)] hover:bg-[var(--surface-subtle)]",
    ].join(" ");
  }
  return [
    "group flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-semibold transition",
    active
      ? "bg-[#183d47] text-white shadow-[inset_3px_0_0_var(--accent)]"
      : "text-[#9ab4ba] hover:bg-[#12303a] hover:text-white",
  ].join(" ");
}

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Điều hướng chính"
      className={mobile ? "grid grid-cols-3 gap-1" : "grid gap-1.5"}
    >
      {navigation.map((item) => {
        const active =
          pathname === item.href || pathname.startsWith(item.href + "/");
        const Icon = item.icon;

        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={navLinkClasses(active, mobile)}
            href={item.href}
            key={item.href}
          >
            <Icon className="size-[19px] shrink-0" />
            <span>{mobile ? item.shortLabel : item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const current =
    navigation.find(
      (item) =>
        pathname === item.href || pathname.startsWith(item.href + "/"),
    ) ?? navigation[0];

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col bg-[var(--navy)] px-4 py-5 lg:flex">
        <div className="px-2">
          <ProductMark />
        </div>
        <div className="mt-9">
          <p className="mb-3 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[#698990]">
            Workspace
          </p>
          <Navigation />
        </div>
        <div className="mt-auto rounded-xl border border-[#22434c] bg-[#102a33] p-3">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#45d3a7] shadow-[0_0_0_4px_rgb(69_211_167/10%)]" />
            <span className="text-xs font-semibold text-[#cae0e4]">
              Data API sẵn sàng
            </span>
          </div>
          <p className="mt-2 text-[11px] leading-5 text-[#78979e]">
            Kết quả dựng sẵn · nuScenes mini
          </p>
        </div>
      </aside>

      <div className="min-w-0 lg:col-start-2">
        <header className="sticky top-0 z-20 border-b border-[var(--line)] bg-white/90 backdrop-blur-xl">
          <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid size-9 place-items-center rounded-[10px] bg-[var(--navy)] text-white lg:hidden">
                <SparkIcon className="size-[18px]" />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-bold text-[var(--foreground)]">
                  {current.label}
                </p>
                <p className="truncate text-[11px] text-[var(--muted)]">
                  ADAS Perception & Sensor Fusion
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden rounded-full border border-[#f0dcb8] bg-[#fff8e9] px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em] text-[#9b6911] sm:inline-flex">
                MVP · Precomputed
              </span>
              <span
                aria-label="Tài khoản Team 27"
                className="grid size-9 place-items-center rounded-full bg-[var(--accent-soft)] text-xs font-bold text-[var(--accent-strong)]"
              >
                T27
              </span>
            </div>
          </div>
          <div className="border-t border-[var(--line)] bg-white px-3 py-2 lg:hidden">
            <Navigation mobile />
          </div>
        </header>

        <main
          className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8"
          id="main-content"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
