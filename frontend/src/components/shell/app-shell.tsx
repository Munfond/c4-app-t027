"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/lab", label: "Lab", number: "01" },
  { href: "/compare", label: "Compare", number: "02" },
  { href: "/benchmarks", label: "Benchmarks", number: "03" },
  { href: "/experiments", label: "Replay Agent", number: "04" },
  { href: "/agent", label: "CARLA Agent", number: "05" },
  { href: "/carla", label: "CARLA Lab", number: "06" },
];

function PerceptionMark() {
  return <svg aria-hidden="true" viewBox="0 0 36 36" fill="none" className="product-mark">
    <path d="M5 13V5h8M23 5h8v8M31 23v8h-8M13 31H5v-8" stroke="currentColor" strokeWidth="2" />
    <path d="m18 10 8 8-8 8-8-8 8-8Z" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="18" cy="18" r="2.5" fill="currentColor" />
  </svg>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return <div className="product-shell">
    <header className="product-header">
      <Link href="/lab" className="product-brand" aria-label="Perception Lab — trang Lab">
        <PerceptionMark />
        <span>perception<span className="brand-suffix"> / lab</span></span>
      </Link>
      <nav aria-label="Điều hướng chính" className="product-nav">
        {navigation.map(item => <Link key={item.href} href={item.href} aria-current={pathname.startsWith(item.href) ? "page" : undefined}>
          <span className="nav-index">{item.number}</span>{item.label}<span className="nav-active-dot" />
        </Link>)}
      </nav>
      <div className="product-edition"><span className="edition-label">ADAS RESEARCH</span><span className="team-stamp">T/27</span></div>
    </header>
    <main id="main-content" className="product-main">{children}</main>
    <footer className="product-footer"><span>PERCEPTION LAB <span className="footer-divider">/</span> TEAM 27 · MUNFOND</span><span>nuScenes mini · Kết quả tính sẵn</span></footer>
  </div>;
}
