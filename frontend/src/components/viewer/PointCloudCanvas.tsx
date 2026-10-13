"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { radarColor, radarSpeed, radarVector3D } from "@/lib/radar";

export type CloudLayer = { id: string; name: string; color: string; points: readonly number[][]; visible: boolean; size?: number; colorBySpeed?: boolean; vectors?: boolean; selectedIndex?: number };

type CachedLayer = { points: readonly number[][]; colorBySpeed?: boolean; group: THREE.Group; object: THREE.Points<THREE.BufferGeometry, THREE.PointsMaterial>; vectors: THREE.LineSegments; selection: THREE.LineSegments };

function disposeGroup(group: THREE.Group) {
  group.traverse(object => {
    const mesh = object as THREE.Mesh;
    mesh.geometry?.dispose();
    if (Array.isArray(mesh.material)) mesh.material.forEach(material => material.dispose());
    else mesh.material?.dispose();
  });
  group.clear();
}

export function PointCloudCanvas({ layers, token, onReady, showLegend = true, onPointSelect }: { layers: CloudLayer[]; token: string; onReady?: (token: string) => void; showLegend?: boolean; onPointSelect?: (layer: string, index: number) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const runtime = useRef<{ camera: THREE.PerspectiveCamera; controls: OrbitControls; content: THREE.Group; render: () => void; layers: Map<string, CachedLayer> } | null>(null);
  const pickCallback = useRef(onPointSelect);
  useEffect(() => { pickCallback.current = onPointSelect; }, [onPointSelect]);
  const [error, setError] = useState("");
  const [view, setView] = useState("3D");
  useEffect(() => {
    if (!host.current) return;
    const element = host.current;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" }); }
    catch { queueMicrotask(() => setError("Không mở được WebGL. Thử trình duyệt khác hoặc bật tăng tốc đồ họa.")); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.setAttribute("role", "img");
    renderer.domElement.setAttribute("aria-label", "LiDAR và Radar cùng hệ tọa độ. Kéo để xoay, cuộn để phóng to; chọn điểm Radar bằng nhấp hoặc danh sách Số đo điểm Radar.");
    renderer.domElement.style.touchAction = "none";
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene(); scene.background = new THREE.Color("#071720");
    const camera = new THREE.PerspectiveCamera(48, 1, .1, 400); camera.position.set(30, 26, 35);
    const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(0, 0, -10); controls.minDistance = 4; controls.maxDistance = 180;
    const content = new THREE.Group(); scene.add(content);
    const grid = new THREE.GridHelper(130, 26, "#3b5961", "#17313a"); grid.position.y = -.05; scene.add(grid);
    const ego = new THREE.Mesh(new THREE.BoxGeometry(1.9, 1.5, 4.5), new THREE.MeshBasicMaterial({ color: "#d9ee98", wireframe: true }));
    ego.position.y = .75; scene.add(ego);
    const rings = new THREE.Group();
    for (const radius of [10, 25, 50]) {
      const vertices = Array.from({ length: 97 }, (_, index) => new THREE.Vector3(Math.cos(index * Math.PI / 48) * radius, .01, Math.sin(index * Math.PI / 48) * radius));
      rings.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(vertices), new THREE.LineBasicMaterial({ color: "#638984", transparent: true, opacity: .35 })));
    }
    scene.add(rings);
    const render = () => renderer.render(scene, camera);
    controls.addEventListener("change", render); controls.update();
    const resize = new ResizeObserver(() => {
      const width = Math.max(1, element.clientWidth), height = Math.max(1, element.clientHeight);
      camera.aspect = width / height; camera.updateProjectionMatrix(); renderer.setSize(width, height); render();
    });
    resize.observe(element);
    runtime.current = { camera, controls, content, render, layers: new Map() };
    let pointerStart: { x: number; y: number } | null = null;
    const pointerDown = (event: PointerEvent) => { pointerStart = { x: event.clientX, y: event.clientY }; };
    const pointerUp = (event: PointerEvent) => {
      if (!pointerStart || Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 5) { pointerStart = null; return; }
      pointerStart = null;
      const radar = runtime.current?.layers.get("radar");
      if (!radar?.group.visible || !pickCallback.current) return;
      const bounds = renderer.domElement.getBoundingClientRect();
      const ray = new THREE.Raycaster(); ray.params.Points.threshold = .8;
      ray.setFromCamera(new THREE.Vector2((event.clientX - bounds.left) / bounds.width * 2 - 1, -(event.clientY - bounds.top) / bounds.height * 2 + 1), camera);
      const hit = ray.intersectObject(radar.object)[0];
      if (hit?.index !== undefined) pickCallback.current("radar", hit.index);
    };
    const pointerCancel = () => { pointerStart = null; };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.domElement.addEventListener("pointercancel", pointerCancel);
    return () => {
      renderer.domElement.removeEventListener("pointerdown", pointerDown); renderer.domElement.removeEventListener("pointerup", pointerUp); renderer.domElement.removeEventListener("pointercancel", pointerCancel);
      resize.disconnect(); controls.removeEventListener("change", render); controls.dispose();
      disposeGroup(content); disposeGroup(rings); grid.geometry.dispose(); (grid.material as THREE.Material).dispose(); ego.geometry.dispose(); ego.material.dispose();
      renderer.dispose(); renderer.domElement.remove(); runtime.current = null;
    };
  }, []);
  useEffect(() => {
    const state = runtime.current;
    if (!state) return;
    for (const [id, cached] of state.layers) {
      if (layers.some(layer => layer.id === id && layer.points === cached.points && layer.colorBySpeed === cached.colorBySpeed)) continue;
      state.content.remove(cached.group); disposeGroup(cached.group); state.layers.delete(id);
    }
    for (const layer of layers) {
      let cached = state.layers.get(layer.id);
      if (!cached) {
        const positions = new Float32Array(layer.points.length * 3);
        const colors = new Float32Array(layer.points.length * 3);
        const vectorPositions: number[] = [], vectorColors: number[] = [];
        layer.points.forEach(([forward, left, up], i) => {
          positions.set([-left, up, -forward], i * 3);
          if (!layer.colorBySpeed) return;
          const point = layer.points[i], color = new THREE.Color(radarColor(point));
          colors.set([color.r, color.g, color.b], i * 3);
          if (radarSpeed(point) < .5) return;
          const { start, end } = radarVector3D(point);
          const angle = Math.atan2(end[2] - start[2], end[0] - start[0]);
          const head = Math.min(.8, radarSpeed(point) * .35);
          vectorPositions.push(...start, ...end,
            end[0] - head * Math.cos(angle - .5), end[1], end[2] - head * Math.sin(angle - .5), ...end,
            end[0] - head * Math.cos(angle + .5), end[1], end[2] - head * Math.sin(angle + .5), ...end);
          for (let vertex = 0; vertex < 6; vertex++) vectorColors.push(color.r, color.g, color.b);
        });
        const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        if (layer.colorBySpeed) geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        const object = new THREE.Points(geometry, new THREE.PointsMaterial({ color: layer.colorBySpeed ? "#ffffff" : layer.color, vertexColors: !!layer.colorBySpeed, size: layer.size ?? .16, sizeAttenuation: true }));
        const vectorGeometry = new THREE.BufferGeometry();
        vectorGeometry.setAttribute("position", new THREE.Float32BufferAttribute(vectorPositions, 3));
        vectorGeometry.setAttribute("color", new THREE.Float32BufferAttribute(vectorColors, 3));
        const vectors = new THREE.LineSegments(vectorGeometry, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: .85 }));
        const selection = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(-.65, 0, 0), new THREE.Vector3(.65, 0, 0), new THREE.Vector3(0, -.65, 0), new THREE.Vector3(0, .65, 0), new THREE.Vector3(0, 0, -.65), new THREE.Vector3(0, 0, .65),
        ]), new THREE.LineBasicMaterial({ color: "#ffffff", depthTest: false }));
        selection.renderOrder = 1;
        const group = new THREE.Group(); group.add(object, vectors, selection); state.content.add(group);
        cached = { points: layer.points, colorBySpeed: layer.colorBySpeed, group, object, vectors, selection }; state.layers.set(layer.id, cached);
      }
      cached.group.visible = layer.visible;
      cached.object.material.size = layer.size ?? .16;
      if (!layer.colorBySpeed) cached.object.material.color.set(layer.color);
      cached.vectors.visible = !!layer.vectors;
      const selected = layer.selectedIndex === undefined ? undefined : layer.points[layer.selectedIndex];
      cached.selection.visible = !!selected;
      if (selected) cached.selection.position.set(-selected[1], selected[2], -selected[0]);
    }
    state.render(); onReady?.(token);
  }, [layers, token, onReady]);

  return <div className="cloud-canvas">
    <div ref={host} className="cloud-host" />
    <div className="cloud-views" role="group" aria-label="Góc nhìn đám mây điểm">
      {([ ["3D", [30, 26, 35]], ["Mặt đường", [14, 8, 20]], ["BEV", [0, 155, -.01]] ] as const).map(([label, position]) => <button type="button" key={label} aria-pressed={view === label} onClick={() => {
        const state = runtime.current; if (!state) return;
        setView(label); state.camera.position.set(position[0], position[1], position[2]); state.controls.target.set(0, 0, label === "BEV" ? 0 : -10); state.controls.update(); state.render();
      }}>{label}</button>)}
    </div>
    {showLegend ? <div className="cloud-legend">{layers.filter(layer => layer.visible && layer.points.length).map(layer => <span key={layer.id}><i style={{ background: layer.color }} />{layer.name} · {layer.points.length.toLocaleString()}</span>)}</div> : null}
    <span className="cloud-instructions">Kéo để xoay · cuộn để zoom · lưới 5 m · vòng 10 / 25 / 50 m</span>
    {error ? <div role="alert" className="stage-message">{error}</div> : null}
  </div>;
}
