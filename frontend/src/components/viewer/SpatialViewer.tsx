"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { detectionToBevBoxTransform } from "@/lib/geometry";
import type { ViewerDetectionFrame, ViewerDetection } from "@/lib/viewer";

type Surface = "ground" | "raised" | "obstacle";
type View = "perspective" | "top" | "side";
type Environment = { points: number[][]; source: string; radius_m: number; voxel_m: number };

const COLORS: Record<Surface, string> = {
  ground: "#2c8f91",
  raised: "#79c6f2",
  obstacle: "#fba668",
};

function insideBox(point: readonly number[], detection: ViewerDetection): boolean {
  const dx = point[0] - detection.center.forward;
  const dy = point[1] - detection.center.left;
  const cosine = Math.cos(detection.yawRadians);
  const sine = Math.sin(detection.yawRadians);
  const localForward = dx * cosine + dy * sine;
  const localLeft = -dx * sine + dy * cosine;
  return Math.abs(localForward) <= detection.size.length / 2 + 0.2
    && Math.abs(localLeft) <= detection.size.width / 2 + 0.2
    && Math.abs(point[2] - detection.center.up) <= detection.size.height / 2 + 0.2;
}

function classify(points: readonly number[][], detections: readonly ViewerDetection[]) {
  // The low quantile near ego estimates the local road surface, not a semantic label.
  const nearHeights = points.filter(([x, y]) => Math.hypot(x, y) < 25).map(point => point[2]).sort((a, b) => a - b);
  const groundHeight = nearHeights[Math.floor(nearHeights.length * 0.15)] ?? -1.5;
  const groups: Record<Surface, number[][]> = { ground: [], raised: [], obstacle: [] };
  for (const point of points) {
    if (point.length !== 3 || !point.every(Number.isFinite)) continue;
    const category = detections.some(detection => insideBox(point, detection))
      ? "obstacle" : point[2] < groundHeight + 0.6 ? "ground" : "raised";
    groups[category].push(point);
  }
  return groups;
}

function disposeTree(root: THREE.Object3D) {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (mesh.geometry) geometries.add(mesh.geometry);
    if (Array.isArray(mesh.material)) mesh.material.forEach(material => materials.add(material));
    else if (mesh.material) materials.add(mesh.material);
  });
  geometries.forEach(geometry => geometry.dispose());
  materials.forEach(material => material.dispose());
}

class SpatialRenderer {
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly controls: OrbitControls;
  private readonly resizeObserver: ResizeObserver;
  private content = new THREE.Group();
  private disposed = false;

  constructor(private readonly host: HTMLElement) {
    this.scene.background = new THREE.Color("#071720");
    this.scene.fog = new THREE.FogExp2("#071720", 0.004);
    this.camera = new THREE.PerspectiveCamera(55, 1, 0.1, 400);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.setAttribute("role", "application");
    this.renderer.domElement.setAttribute("aria-label", "Bản đồ 3D LiDAR, kéo để xoay, cuộn để phóng to");
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    this.renderer.domElement.style.display = "block";
    host.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.minDistance = 10;
    this.controls.maxDistance = 180;
    this.controls.minPolarAngle = 0.05;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.03;
    this.controls.target.set(0, 0, -12);
    this.controls.addEventListener("change", this.render);
    this.setView("perspective");

    this.scene.add(new THREE.HemisphereLight("#d4f3ff", "#0d2630", 2));
    const sun = new THREE.DirectionalLight("#ffffff", 1.6);
    sun.position.set(-25, 60, -20);
    this.scene.add(sun);

    const grid = new THREE.GridHelper(130, 26, "#31525c", "#17313d");
    grid.position.y = -1.65;
    this.scene.add(grid);
    for (const radius of [10, 25, 50]) {
      const vertices = Array.from({ length: 129 }, (_, index) => {
        const angle = index * Math.PI * 2 / 128;
        return new THREE.Vector3(Math.cos(angle) * radius, -1.62, Math.sin(angle) * radius);
      });
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(vertices),
        new THREE.LineBasicMaterial({ color: "#448391", transparent: true, opacity: 0.4 }));
      this.scene.add(line);
    }
    const ego = new THREE.Mesh(new THREE.BoxGeometry(1.9, 1.5, 4.5),
      new THREE.MeshLambertMaterial({ color: "#ecf7f8", transparent: true, opacity: 0.8 }));
    ego.position.y = -0.55;
    this.scene.add(ego);
    const forward = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1),
      new THREE.Vector3(0, 0.6, -2.5), 4, "#3df0da", 1, 0.55);
    this.scene.add(forward);

    this.scene.add(this.content);
    this.resizeObserver = new ResizeObserver(() => {
      if (this.disposed) return;
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height, false);
      this.render();
    });
    this.resizeObserver.observe(host);
  }

  setView(view: View) {
    if (view === "top") this.camera.position.set(0, 92, -22);
    else if (view === "side") this.camera.position.set(75, 22, -12);
    else this.camera.position.set(46, 39, 54);
    this.controls.update();
    this.render();
  }

  setData(points: readonly number[][], detections: readonly ViewerDetection[]): Record<Surface, number> {
    this.scene.remove(this.content);
    disposeTree(this.content);
    this.content = new THREE.Group();
    const groups = classify(points, detections);
    let cube: THREE.BoxGeometry | null = null;
    const transform = new THREE.Object3D();
    for (const surface of ["ground", "raised", "obstacle"] as const) {
      const selected = groups[surface];
      if (!selected.length) continue;
      cube ??= new THREE.BoxGeometry(0.3, 0.3, 0.3);
      const material = new THREE.MeshLambertMaterial({ color: COLORS[surface] });
      const voxels = new THREE.InstancedMesh(cube, material, selected.length);
      selected.forEach(([forward, left, up], index) => {
        transform.position.set(-left, up, -forward);
        transform.updateMatrix();
        voxels.setMatrixAt(index, transform.matrix);
      });
      voxels.instanceMatrix.needsUpdate = true;
      voxels.frustumCulled = false;
      this.content.add(voxels);
    }
    for (const detection of detections) {
      const shape = detectionToBevBoxTransform(detection);
      const geometry = new THREE.BoxGeometry(shape.size.x, shape.size.y, shape.size.z);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: "#ffb77a", transparent: true, opacity: 0.9 }));
      edges.position.set(shape.position.x, shape.position.y, shape.position.z);
      edges.rotation.y = shape.rotationYRadians;
      this.content.add(edges);
      geometry.dispose();
    }
    this.scene.add(this.content);
    // Instanced meshes share one cube geometry, disposed on the next update.
    this.render();
    return { ground: groups.ground.length, raised: groups.raised.length, obstacle: groups.obstacle.length };
  }

  private render = () => {
    if (!this.disposed) this.renderer.render(this.scene, this.camera);
  };

  dispose() {
    this.disposed = true;
    this.resizeObserver.disconnect();
    this.controls.removeEventListener("change", this.render);
    this.controls.dispose();
    disposeTree(this.scene);
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

type SpatialViewerProps = {
  frame: ViewerDetectionFrame | null;
  sampleToken: string | null;
  nextToken?: string;
  requestError?: string | null;
  onFrameReady?: (token: string) => void;
  onFrameError?: () => void;
};

export function SpatialViewer({ frame, sampleToken: token, nextToken, requestError, onFrameReady, onFrameError }: SpatialViewerProps) {
  const host = useRef<HTMLDivElement>(null);
  const spatial = useRef<SpatialRenderer | null>(null);
  const environmentCache = useRef(new Map<string, Environment>());
  const [environment, setEnvironment] = useState<{ token: string; value: Environment } | null>(null);
  const [error, setError] = useState("");
  const [rendererError, setRendererError] = useState("");
  const [view, setView] = useState<View>("perspective");
  const [counts, setCounts] = useState<Record<Surface, number> | null>(null);
  const [renderedToken, setRenderedToken] = useState<string | null>(null);

  const rememberEnvironment = useCallback((key: string, value: Environment) => {
    const cache = environmentCache.current;
    cache.set(key, value);
    while (cache.size > 6) cache.delete(cache.keys().next().value!);
  }, []);

  useEffect(() => {
    if (!host.current) return;
    try { spatial.current = new SpatialRenderer(host.current); }
    catch (cause) {
      queueMicrotask(() => setRendererError(cause instanceof Error ? cause.message : "Không mở được bản đồ 3D"));
      onFrameError?.();
    }
    return () => { spatial.current?.dispose(); spatial.current = null; };
  }, [onFrameError]);

  useEffect(() => {
    const controller = new AbortController();
    const cached = token ? environmentCache.current.get(token) : null;
    if (!cached) {
      spatial.current?.setData([], []);
      queueMicrotask(() => { if (!controller.signal.aborted) { setCounts(null); setError(""); } });
    }
    if (!token) return;
    if (cached) {
      queueMicrotask(() => { if (!controller.signal.aborted) { setEnvironment({ token, value: cached }); setError(""); } });
      return () => controller.abort();
    }
    void fetch(`/api/v1/lab/frames/${encodeURIComponent(token)}/environment`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(`LiDAR chưa sẵn sàng (HTTP ${response.status})`);
        return response.json() as Promise<Environment>;
      })
      .then(value => {
        if (controller.signal.aborted) return;
        rememberEnvironment(token, value);
        setEnvironment({ token, value });
        setError("");
      })
      .catch(cause => {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Lỗi tải LiDAR");
        onFrameError?.();
      });
    return () => controller.abort();
  }, [token, rememberEnvironment, onFrameError]);

  useEffect(() => {
    if (!nextToken || nextToken === token || environmentCache.current.has(nextToken)) return;
    const controller = new AbortController();
    void fetch(`/api/v1/lab/frames/${encodeURIComponent(nextToken)}/environment`, { signal: controller.signal })
      .then(response => response.ok ? response.json() as Promise<Environment> : null)
      .then(value => { if (!controller.signal.aborted && value) rememberEnvironment(nextToken, value); })
      .catch(() => { /* Prefetch failure is retried when the frame becomes current. */ });
    return () => controller.abort();
  }, [nextToken, token, rememberEnvironment]);

  useEffect(() => {
    if (!token || environment?.token !== token || frame?.frame.sampleToken !== token || !spatial.current) return;
    const result = spatial.current.setData(environment.value.points, frame?.detections ?? []);
    queueMicrotask(() => { setCounts(result); setRenderedToken(token); onFrameReady?.(token); });
  }, [environment, frame, token, onFrameReady]);

  const visibleError = rendererError || error || requestError;
  return <section aria-busy={renderedToken !== token && !visibleError} className="relative h-full min-h-[520px] overflow-hidden bg-[#071720] text-white">
    <div ref={host} className="absolute inset-0" />
    <div className="pointer-events-none absolute left-4 top-4 max-w-[calc(100%-2rem)] rounded-xl border border-white/15 bg-[#071720]/85 px-4 py-3 shadow-xl backdrop-blur sm:max-w-[55%]">
      <p className="text-sm font-semibold text-white">Bản đồ 3D quanh xe</p>
      <p className="mt-1 text-xs text-slate-300">{environment && environment.token === token ? `${environment.value.points.length.toLocaleString()} điểm LiDAR thật · ${frame?.detections.length ?? 0} hộp vật cản` : "Đang tải LiDAR…"}</p>
      <p className="mt-1 text-[11px] text-slate-400">Quan sát bề mặt và phân nhóm hình học; vùng khuất chưa được dự đoán.</p>
    </div>
    <div className="absolute right-4 top-28 flex gap-1 rounded-lg border border-white/15 bg-[#071720]/85 p-1 text-xs shadow-xl backdrop-blur sm:top-4">
      {([ ["perspective", "Góc 3D"], ["top", "Từ trên"], ["side", "Nhìn ngang"] ] as const).map(([value, label]) =>
        <button key={value} type="button" onClick={() => { setView(value); spatial.current?.setView(value); }}
          className={`rounded-md px-2.5 py-1.5 transition ${view === value ? "bg-teal-500 text-slate-950" : "text-slate-200 hover:bg-white/10"}`}>{label}</button>)}
    </div>
    <div className="pointer-events-none absolute bottom-4 left-4 rounded-xl border border-white/15 bg-[#071720]/85 px-4 py-3 text-xs shadow-xl backdrop-blur">
      <p className="mb-2 font-semibold">Phân nhóm bề mặt</p>
      {([ ["ground", "Mặt thấp"], ["raised", "Khối cao / bề mặt dựng"], ["obstacle", "Trong hộp vật cản"] ] as const).map(([key, label]) =>
        <p className="mt-1 flex items-center gap-2" key={key}><span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS[key] }} />{label}{counts ? ` · ${counts[key].toLocaleString()}` : ""}</p>)}
      <p className="mt-2 text-[10px] text-slate-400">Kéo để xoay · cuộn để zoom · nhấp phải để dịch chuyển</p>
    </div>
    {visibleError ? <div role="alert" className="absolute inset-0 grid place-items-center bg-[#071720]/90 p-6 text-center text-sm text-rose-300">{visibleError}</div>
      : renderedToken !== token ? <div role="status" className="absolute inset-0 grid place-items-center bg-[#071720]/95 p-6 text-center text-sm text-slate-200">Đang đồng bộ LiDAR và vật cản của frame…</div> : null}
  </section>;
}
