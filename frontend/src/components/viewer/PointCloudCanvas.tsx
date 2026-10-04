"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export type CloudLayer = { id: string; name: string; color: string; points: readonly number[][]; visible: boolean; size?: number };

function disposeGroup(group: THREE.Group) {
  group.traverse(object => {
    const mesh = object as THREE.Mesh;
    mesh.geometry?.dispose();
    if (Array.isArray(mesh.material)) mesh.material.forEach(material => material.dispose());
    else mesh.material?.dispose();
  });
  group.clear();
}

export function PointCloudCanvas({ layers, token, onReady }: { layers: CloudLayer[]; token: string; onReady?: (token: string) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const runtime = useRef<{ camera: THREE.PerspectiveCamera; controls: OrbitControls; content: THREE.Group; render: () => void } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!host.current) return;
    const element = host.current;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" }); }
    catch { queueMicrotask(() => setError("Không mở được WebGL. Thử trình duyệt khác hoặc bật tăng tốc đồ họa.")); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.setAttribute("aria-label", "Đám mây điểm 3D. Kéo để xoay, cuộn để phóng to.");
    renderer.domElement.style.touchAction = "none";
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene(); scene.background = new THREE.Color("#071720");
    const camera = new THREE.PerspectiveCamera(48, 1, .1, 400); camera.position.set(30, 26, 35);
    const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(0, 0, -10); controls.minDistance = 4; controls.maxDistance = 180;
    const content = new THREE.Group(); scene.add(content);
    const grid = new THREE.GridHelper(130, 26, "#3b5961", "#17313a"); grid.position.y = -1.75; scene.add(grid);
    const ego = new THREE.Mesh(new THREE.BoxGeometry(1.9, 1.5, 4.5), new THREE.MeshBasicMaterial({ color: "#d9ee98", wireframe: true }));
    ego.position.y = -1; scene.add(ego);
    const render = () => renderer.render(scene, camera);
    controls.addEventListener("change", render); controls.update();
    const resize = new ResizeObserver(() => {
      const width = Math.max(1, element.clientWidth), height = Math.max(1, element.clientHeight);
      camera.aspect = width / height; camera.updateProjectionMatrix(); renderer.setSize(width, height); render();
    });
    resize.observe(element);
    runtime.current = { camera, controls, content, render };
    return () => {
      resize.disconnect(); controls.removeEventListener("change", render); controls.dispose();
      disposeGroup(content); grid.geometry.dispose(); (grid.material as THREE.Material).dispose(); ego.geometry.dispose(); ego.material.dispose();
      renderer.dispose(); renderer.domElement.remove(); runtime.current = null;
    };
  }, []);
  useEffect(() => {
    const state = runtime.current;
    if (!state) return;
    disposeGroup(state.content);
    for (const layer of layers.filter(item => item.visible)) {
      const positions = new Float32Array(layer.points.length * 3);
      layer.points.forEach(([forward, left, up], i) => positions.set([-left, up, -forward], i * 3));
      const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      state.content.add(new THREE.Points(geometry, new THREE.PointsMaterial({ color: layer.color, size: layer.size ?? .16, sizeAttenuation: true })));
    }
    state.render(); onReady?.(token);
  }, [layers, token, onReady]);

  return <div className="cloud-canvas">
    <div ref={host} className="cloud-host" />
    <div className="cloud-views" role="group" aria-label="Góc nhìn đám mây điểm">
      {([ ["3D", [30, 26, 35]], ["BEV", [0, 90, -9.99]] ] as const).map(([label, position]) => <button type="button" key={label} onClick={() => {
        const state = runtime.current; if (!state) return;
        state.camera.position.set(position[0], position[1], position[2]); state.controls.target.set(0, 0, -10); state.controls.update(); state.render();
      }}>{label}</button>)}
    </div>
    <div className="cloud-legend">{layers.map(layer => <span key={layer.id} data-hidden={!layer.visible}><i style={{ background: layer.color }} />{layer.name} · {layer.points.length.toLocaleString()}</span>)}</div>
    <span className="cloud-instructions">Kéo để xoay · cuộn để phóng to · xe tham chiếu màu vàng</span>
    {error ? <div role="alert" className="stage-message">{error}</div> : null}
  </div>;
}
