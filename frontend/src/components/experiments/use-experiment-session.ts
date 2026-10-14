"use client";

import { useEffect, useState } from "react";

const base = "/api/v1/experiments/sessions";
const key = "p027-experiment-session";
let initialization: Promise<string> | null = null;
class SessionExpired extends Error {}

async function request(path: string) {
  const response = await fetch(`${base}${path}`, { method: "POST" });
  if (response.status === 410) throw new SessionExpired("Phiên đã hết hạn.");
  if (!response.ok) throw new Error("Không kết nối được phiên thí nghiệm.");
  return response.json() as Promise<{ id: string }>;
}

async function initialize() {
  const mode = await fetch("/api/v1/evidence/capabilities");
  if (!mode.ok) throw new Error("Không kiểm tra được chế độ thí nghiệm.");
  const capability = await mode.json() as { interactive_enabled: boolean };
  if (!capability.interactive_enabled) throw new Error("Phiên bản xem kết quả; tạo thí nghiệm chưa được bật trên server này.");
  const saved = sessionStorage.getItem(key);
  if (saved) {
    try { await request(`/${saved}/touch`); return saved; }
    catch (cause) { if (cause instanceof SessionExpired) sessionStorage.removeItem(key); else throw cause; }
  }
  const data = await request("");
  sessionStorage.setItem(key, data.id);
  return data.id;
}

export type ExperimentSessionState = ReturnType<typeof useExperimentSession>;

export function useExperimentSession(enabled = true) {
  const [session, setSession] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    initialization ??= initialize();
    void initialization.then(id => { if (!disposed) { setSession(id); setLoading(false); } })
      .catch(cause => { initialization = null; if (!disposed) { setError(String(cause)); setLoading(false); } });
    return () => { disposed = true; };
  }, [enabled]);
  useEffect(() => {
    if (!session) return;
    let disposed = false;
    const renew = async () => {
      try { await request(`/${session}/touch`); if (!disposed) setError(""); }
      catch (cause) {
        if (!disposed) {
          setError(cause instanceof SessionExpired ? "Phiên đã hết hạn. Bắt đầu phiên mới để tiếp tục." : "Kết nối đang gián đoạn. Đang thử lại; lịch sử phiên vẫn được giữ.");
          if (cause instanceof SessionExpired) { setSession(""); sessionStorage.removeItem(key); initialization = null; }
        }
      }
    };
    const visible = () => { if (!document.hidden) void renew(); };
    const suspend = () => { navigator.sendBeacon(`${base}/${session}/suspend`); };
    const timer = setInterval(() => void renew(), 20000);
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("pagehide", suspend);
    window.addEventListener("beforeunload", suspend);
    return () => { disposed = true; clearInterval(timer); document.removeEventListener("visibilitychange", visible); window.removeEventListener("pagehide", suspend); window.removeEventListener("beforeunload", suspend); };
  }, [session]);
  const end = async () => {
    setLoading(true); setError("");
    try {
      await request(`/${session}/end`);
      sessionStorage.removeItem(key); initialization = null; setSession("");
    } catch (cause) { setError(String(cause)); }
    finally { setLoading(false); }
  };
  const start = async () => {
    setLoading(true); setError("");
    try { initialization = initialize(); setSession(await initialization); }
    catch (cause) { initialization = null; setError(String(cause)); }
    finally { setLoading(false); }
  };
  return { session, loading, error, end, start };
}
