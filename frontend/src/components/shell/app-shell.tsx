"use client";

import Link from "next/link";
import { UsageGuide } from "@/components/help/usage-guide";
import dynamic from "next/dynamic";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { ExperimentSource, Inspection } from "@/components/experiments/agent-panel";
import type { ExperimentSpec } from "@/components/experiments/experiment-workspace";
import { EvidenceViewport } from "@/components/experiments/evidence-viewport";
import { useExperimentSession } from "@/components/experiments/use-experiment-session";

const AgentPanel = dynamic(() => import("@/components/experiments/agent-panel"), { loading: () => <p className="agent-panel-body" role="status">Đang kết nối agent…</p> });
const ManualWorkspace = dynamic(() => import("@/components/experiments/experiment-workspace").then(module => module.ExperimentWorkspace), { loading: () => <p role="status">Đang mở cấu hình nâng cao…</p> });
const NativeOnlinePreview = dynamic(() => import("@/components/experiments/native-online-evidence").then(module => module.NativeOnlinePreview), { loading: () => <p role="status">Đang mở capture PPO…</p> });
const ReplayWorkspace = dynamic(() => import("@/components/experiments/replay-workspace").then(module => module.ReplayWorkspace), { loading: () => <p role="status">Đang mở lịch sử replay…</p> });

const navigation = [
  { href: "/lab", label: "Lab", number: "01" },
  { href: "/compare", label: "Compare", number: "02" },
  { href: "/benchmarks", label: "Benchmarks", number: "03" },
];

// Keep old bookmarks useful without creating a fourth navigation destination.
function AgentEntry({ onOpen }: { onOpen: (source: ExperimentSource, tools: boolean) => void }) {
  const params = useSearchParams();
  const source = params.get("agent");
  const tools = params.get("tools") === "manual" || params.get("tools") === "history";
  useEffect(() => {
    if (source === "carla" || source === "dataset_replay") onOpen(source, tools);
  }, [source, tools, onOpen]);
  return null;
}

function PerceptionMark() {
  return <svg aria-hidden="true" viewBox="0 0 36 36" fill="none" className="product-mark">
    <path d="M5 13V5h8M23 5h8v8M31 23v8h-8M13 31H5v-8" stroke="currentColor" strokeWidth="2" />
    <path d="m18 10 8 8-8 8-8-8 8-8Z" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="18" cy="18" r="2.5" fill="currentColor" />
  </svg>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [source, setSource] = useState<ExperimentSource>("dataset_replay");
  const [toolsOpen, setToolsOpen] = useState(false);
  const [toolsVisited, setToolsVisited] = useState(false);
  const [toolMode, setToolMode] = useState<"manual" | "history" | "online">("history");
  const [onlinePreview, setOnlinePreview] = useState<string | undefined>();
  const [capturePreview, setCapturePreview] = useState<string | undefined>();
  const [draft, setDraft] = useState<{ spec: ExperimentSpec; revision: number } | null>(null);
  const sessionState = useExperimentSession(mounted);
  const visibleInspection = inspection && (!inspection.session || inspection.session === sessionState.session) ? inspection : null;
  const origin = visibleInspection?.source ?? (toolsOpen ? source : "precomputed");
  const launcher = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const toolsBack = useRef<HTMLButtonElement>(null);
  const main = useRef<HTMLElement>(null);
  const close = () => { setOpen(false); launcher.current?.focus(); };
  const show = () => { setMounted(true); setOpen(true); };
  const openTools = (spec?: ExperimentSpec, mode?: "manual" | "history") => {
    setCapturePreview(undefined); setOnlinePreview(undefined);
    setToolMode(source === "carla" || spec || mode === "manual" ? "manual" : "history");
    setToolsVisited(true); setToolsOpen(true); setInspection(null);
    if (spec) {
      setSource(spec.source === "carla" ? "carla" : "dataset_replay");
      setDraft(previous => ({ spec, revision: (previous?.revision ?? 0) + 1 }));
    }
    window.dispatchEvent(new Event("p027-pause-lab"));
  };
  const openEntry = useCallback((entrySource: ExperimentSource, tools: boolean) => {
    setSource(entrySource); setMounted(true); setOpen(true);
    setToolMode(entrySource === "carla" ? "manual" : "history");
    if (tools) { setToolsVisited(true); setToolsOpen(true); }
  }, []);
  const returnToLab = () => { setToolsOpen(false); setInspection(null); main.current?.focus(); };
  useEffect(() => {
    if (open) closeButton.current?.focus();
    const showAgent = () => { setMounted(true); setOpen(true); };
    const escape = (event: KeyboardEvent) => { if (open && event.key === "Escape") { setOpen(false); launcher.current?.focus(); } };
    window.addEventListener("p027-open-agent", showAgent);
    window.addEventListener("keydown", escape);
    return () => { window.removeEventListener("p027-open-agent", showAgent); window.removeEventListener("keydown", escape); };
  }, [open]);
  useEffect(() => { if (toolsOpen) toolsBack.current?.focus(); }, [toolsOpen]);
  return <div className="product-shell" data-agent-open={open}>
    <Suspense fallback={null}><AgentEntry onOpen={openEntry} /></Suspense>
    <header className="product-header">
      <Link href="/lab" className="product-brand" aria-label="Perception Lab — trang Lab" onClick={() => { setInspection(null); setToolsOpen(false); }}>
        <PerceptionMark />
        <span>perception<span className="brand-suffix"> / lab</span></span>
      </Link>
      <nav aria-label="Điều hướng chính" className="product-nav">
        {navigation.map(item => <Link key={item.href} href={item.href} onClick={() => { setInspection(null); setToolsOpen(false); }} aria-current={pathname.startsWith(item.href) ? "page" : undefined}>
          <span className="nav-index">{item.number}</span>{item.label}<span className="nav-active-dot" />
        </Link>)}
      </nav>
      <div className="product-edition"><UsageGuide onShowLab={() => { setToolsOpen(false); setInspection(null); }} onShowAgent={() => { setToolsOpen(false); setInspection(null); openEntry("carla", false); }} /><span className="edition-label">ADAS RESEARCH</span><span className="team-stamp">T/27</span></div>
    </header>
    <div className="agent-workspace-layout">
      <main ref={main} id="main-content" className="product-main" tabIndex={-1}>
        {visibleInspection && <EvidenceViewport key={`${visibleInspection.study}:${visibleInspection.candidate.job_id}:${visibleInspection.model}`} inspection={visibleInspection} onClose={() => setInspection(null)} />}
        <section id="agent-tools" hidden={!toolsOpen || !!visibleInspection} aria-label="Công cụ thí nghiệm">
          <div className="experiment-toolbar"><button ref={toolsBack} type="button" onClick={returnToLab}>← Quay lại bản đồ</button><span>{toolMode === "online" ? "CARLA / Kiểm chứng PPO trực tiếp" : source === "carla" ? "CARLA / Cấu hình nâng cao" : toolMode === "manual" ? "nuScenes / Cấu hình nâng cao" : "nuScenes / Lịch sử & kết quả"}</span></div>
          {toolsVisited && (toolMode === "online" && onlinePreview
            ? <NativeOnlinePreview key={onlinePreview} run={onlinePreview} active={toolsOpen && !visibleInspection} />
            : toolMode === "manual"
            ? <ManualWorkspace key={`${source}:${draft?.revision ?? 0}:${capturePreview ?? ""}`} source={source === "carla" ? "carla" : "nuscenes"} initialSpec={draft?.spec} initialJobId={capturePreview} active={toolsOpen && !visibleInspection} />
            : <ReplayWorkspace sessionState={sessionState} active={toolsOpen && !visibleInspection} />)}
        </section>
        <div hidden={!!visibleInspection || toolsOpen}>{children}</div>
      </main>
      <aside id="perception-agent" aria-label="Perception agent" className="agent-dock" hidden={!open}>
        <header className="agent-dock-header"><div><span className="eyebrow">PERCEPTION ASSISTANT</span><h2>Hỏi. Đo. Đối chiếu.</h2></div><button ref={closeButton} onClick={close} aria-label="Thu gọn agent">×</button></header>
        {mounted && <AgentPanel key={source === "dataset_replay" ? `replay:${sessionState.session}` : "carla"} source={source} active={open} sessionState={sessionState} toolsOpen={toolsOpen && !visibleInspection} onOpenTools={openTools} onOpenOnline={run => { setSource("carla"); setDraft(null); setCapturePreview(undefined); setOnlinePreview(run); setToolMode("online"); setToolsVisited(true); setToolsOpen(true); setInspection(null); window.dispatchEvent(new Event("p027-pause-lab")); requestAnimationFrame(() => main.current?.focus()); }} onOpenCapture={job => { setSource("carla"); setDraft(null); setCapturePreview(job); setOnlinePreview(undefined); setToolMode("manual"); setToolsVisited(true); setToolsOpen(true); setInspection(null); window.dispatchEvent(new Event("p027-pause-lab")); requestAnimationFrame(() => main.current?.focus()); }} onSourceChange={value => { setSource(value); setCapturePreview(undefined); setOnlinePreview(undefined); setInspection(null); setDraft(null); setToolMode(value === "carla" ? "manual" : "history"); }} onInspect={value => { setInspection(value); window.dispatchEvent(new Event("p027-pause-lab")); requestAnimationFrame(() => main.current?.focus()); }} />}
      </aside>
    </div>
    <button ref={launcher} className="agent-launcher" aria-expanded={open} aria-controls="perception-agent" aria-label={open ? "Thu gọn Perception agent" : "Mở Perception agent"} onClick={open ? close : show}>
      <svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M20 5v6M16 5h8M9 16a5 5 0 0 1 5-5h12a5 5 0 0 1 5 5v12a5 5 0 0 1-5 5H14a5 5 0 0 1-5-5V16Z" stroke="currentColor" strokeWidth="2"/><path d="M5 19v7M35 19v7M16 27h8" stroke="currentColor" strokeWidth="2"/><circle cx="15" cy="20" r="2" fill="currentColor"/><circle cx="25" cy="20" r="2" fill="currentColor"/></svg><span>Agent<span>Evidence first</span></span>
    </button>
    <footer className="product-footer"><span>PERCEPTION LAB <span className="footer-divider">/</span> TEAM 27 · MUNFOND</span><span>{origin === "carla" ? "CARLA · Kết quả thí nghiệm" : origin === "dataset_replay" ? "nuScenes · Replay dữ liệu ghi sẵn" : "nuScenes mini · Kết quả tính sẵn"}</span></footer>
  </div>;
}
