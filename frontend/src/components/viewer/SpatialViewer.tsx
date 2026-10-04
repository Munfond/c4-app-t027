"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { detectionToBevBoxTransform } from "@/lib/geometry";
import { loadEnvironmentFrame, type EnvironmentFrame } from "@/lib/lab-frame-cache";
import type { ViewerDetectionFrame, ViewerDetection } from "@/lib/viewer";
import { reconstructSpatialSurfaces, type SpatialSurface, type SpatialSurfaces } from "@/lib/viewer/spatial-surfaces";
import { SpatialObjectFactory, objectForm } from "@/lib/viewer/spatial-objects";

type Surface = SpatialSurface;
type View = "perspective" | "top" | "side" | "near";
type Representation = "surface" | "points";
type SceneCounts = Record<Surface, number> & { cars: number; people: number; others: number; facades: number; groundPatches: number };

const COLORS: Record<Surface, string> = { ground: "#689b98", raised: "#afc2ce", obstacle: "#ffbe78" };
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
  private readonly objects = new SpatialObjectFactory();
  private readonly grid: THREE.GridHelper;
  private readonly rings = new THREE.Group();
  private readonly ego: THREE.Group;
  private readonly forward: THREE.ArrowHelper;
  private content = new THREE.Group();
  private objectContent = new THREE.Group();
  private surfaces: SpatialSurfaces | null = null;
  private detections: readonly ViewerDetection[] = [];
  private representation: Representation = "surface";
  private showBoxes = false;
  private disposed = false;

  constructor(private readonly host: HTMLElement) {
    this.scene.background = new THREE.Color("#071720");
    this.scene.fog = new THREE.FogExp2("#071720", 0.003);
    this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 400);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.setAttribute("role", "application");
    this.renderer.domElement.setAttribute("aria-label", "Bản đồ 3D LiDAR và hình đại diện vật thể, kéo để xoay, cuộn để phóng to");
    Object.assign(this.renderer.domElement.style, { width: "100%", height: "100%", display: "block" });
    host.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.minDistance = 6;
    this.controls.maxDistance = 180;
    this.controls.minPolarAngle = 0.05;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.03;
    this.controls.target.set(0, 0, -10);
    this.controls.addEventListener("change", this.render);
    this.scene.add(new THREE.HemisphereLight("#dceaf6", "#304c47", 2));
    const sun = new THREE.DirectionalLight("#fff1dc", 2.2);
    sun.position.set(-25, 60, -20); this.scene.add(sun);
    this.grid = new THREE.GridHelper(130, 26, "#294b57", "#132c36"); this.scene.add(this.grid);
    for (const radius of [10, 25, 50]) {
      const vertices = Array.from({ length: 129 }, (_, index) => {
        const angle = index * Math.PI * 2 / 128;
        return new THREE.Vector3(Math.cos(angle) * radius, 0, Math.sin(angle) * radius);
      });
      this.rings.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(vertices), new THREE.LineBasicMaterial({ color: "#638984", transparent: true, opacity: 0.32 })));
    }
    this.scene.add(this.rings);
    this.ego = this.objects.create({ id:"ego",className:"car",center:{forward:0,left:0,up:.75},size:{width:1.9,height:1.5,length:4.5},yawRadians:0,velocity:{forward:0,left:0},confidence:1 }, "#d9ee98");
    this.scene.add(this.ego);
    this.forward = new THREE.ArrowHelper(new THREE.Vector3(0,0,-1), new THREE.Vector3(0,.2,-2.7), 3, "#d9ee98", .7, .4);
    this.scene.add(this.forward);
    this.scene.add(this.content, this.objectContent);
    this.setView("perspective");
    this.resizeObserver = new ResizeObserver(() => {
      if (this.disposed) return;
      const width = Math.max(host.clientWidth,1), height = Math.max(host.clientHeight,1);
      this.camera.aspect = width/height; this.camera.updateProjectionMatrix(); this.renderer.setSize(width,height,false); this.render();
    });
    this.resizeObserver.observe(host);
  }

  setView(view: View) {
    this.controls.target.set(0,this.surfaces?.groundHeight ?? 0,-10);
    if (view === "near") {
      const nearest = [...this.detections].sort((a,b) => Math.hypot(a.center.forward,a.center.left)-Math.hypot(b.center.forward,b.center.left))[0];
      if (nearest) this.controls.target.set(-nearest.center.left,nearest.center.up,-nearest.center.forward);
      this.camera.position.copy(this.controls.target).add(new THREE.Vector3(9,5,9));
    }
    else if (view === "top") this.camera.position.set(0,78,-10);
    else if (view === "side") this.camera.position.set(48,14,-10);
    else this.camera.position.set(30,24,35);
    this.controls.update(); this.render();
  }

  setOptions(representation: Representation, showBoxes: boolean) {
    if (representation === this.representation && showBoxes === this.showBoxes) return;
    this.representation = representation; this.showBoxes = showBoxes; this.rebuild();
  }

  setData(points: readonly number[][], detections: readonly ViewerDetection[]): SceneCounts {
    this.surfaces = reconstructSpatialSurfaces(points,detections); this.detections = detections;
    const { groundHeight, groups, facades, groundVertices } = this.surfaces;
    this.grid.position.y = groundHeight - .08;
    this.rings.position.y = groundHeight + .012;
    this.ego.position.y = groundHeight;
    this.forward.position.y = groundHeight + .2;
    this.rebuild();
    return {
      ground:groups.ground.length,raised:groups.raised.length,obstacle:groups.obstacle.length,
      cars:detections.filter(d=>objectForm(d.className)==="vehicle").length,
      people:detections.filter(d=>objectForm(d.className)==="person").length,
      others:detections.filter(d=>objectForm(d.className)==="other").length,
      facades:facades.length,groundPatches:groundVertices.length/18,
    };
  }

  private addPoints(points: readonly number[][], color: string, size: number, opacity = 1) {
    if (!points.length) return;
    const vertices = new Float32Array(points.length*3);
    points.forEach(([f,l,u],i) => { vertices[i*3]=-l;vertices[i*3+1]=u;vertices[i*3+2]=-f; });
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position",new THREE.BufferAttribute(vertices,3));
    this.content.add(new THREE.Points(geometry,new THREE.PointsMaterial({color,size,sizeAttenuation:true,transparent:opacity<1,opacity,depthWrite:opacity===1})));
  }

  private rebuild() {
    this.scene.remove(this.content,this.objectContent); disposeTree(this.content);
    // Object primitives belong to the shared factory and survive frame changes.
    this.objectContent.clear(); this.content = new THREE.Group();
    if (!this.surfaces) { this.scene.add(this.content,this.objectContent); return; }
    const {groups,facades,groundVertices} = this.surfaces;
    if (this.representation === "surface") {
      if (groundVertices.length) {
        const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position",new THREE.Float32BufferAttribute(groundVertices,3)); geometry.computeVertexNormals();
        this.content.add(new THREE.Mesh(geometry,new THREE.MeshLambertMaterial({color:"#3b5c62",side:THREE.DoubleSide})));
      }
      if (facades.length) {
        const walls = new THREE.InstancedMesh(new THREE.BoxGeometry(1,1,1),new THREE.MeshLambertMaterial({color:"#879fae"}),facades.length);
        const transform = new THREE.Object3D();
        facades.forEach((patch,index) => {
          transform.position.set(-patch.left,patch.bottom+patch.height/2,-patch.forward);
          transform.scale.set(.10,patch.height,patch.length); transform.rotation.y=patch.yaw; transform.updateMatrix(); walls.setMatrixAt(index,transform.matrix);
        });
        walls.instanceMatrix.needsUpdate=true; walls.frustumCulled=false; this.content.add(walls);
      }
      this.addPoints(groups.ground,"#7baba9",.07,.35);
      this.addPoints(groups.raised,"#abc4d2",.16,.8);
      for (const detection of this.detections) {
        const form = objectForm(detection.className);
        const color = form === "person" ? "#ffbf83" : form === "vehicle" ? "#81d2ce" : "#b6bfbe";
        this.objectContent.add(this.objects.create(detection,color));
      }
    } else {
      for (const surface of ["ground","raised","obstacle"] as const) this.addPoints(groups[surface],COLORS[surface],.20);
    }
    if (this.showBoxes) for (const detection of this.detections) {
      const shape = detectionToBevBoxTransform(detection), geometry = new THREE.BoxGeometry(shape.size.x,shape.size.y,shape.size.z);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry),new THREE.LineBasicMaterial({color:"#e4dda7",transparent:true,opacity:.6}));
      edges.position.set(shape.position.x,shape.position.y,shape.position.z);edges.rotation.y=shape.rotationYRadians;this.content.add(edges);geometry.dispose();
    }
    this.scene.add(this.content,this.objectContent); this.render();
  }

  private render = () => { if (!this.disposed) this.renderer.render(this.scene,this.camera); };
  dispose() {
    this.disposed=true;this.resizeObserver.disconnect();this.controls.removeEventListener("change",this.render);this.controls.dispose();
    this.scene.remove(this.objectContent,this.ego); disposeTree(this.scene);this.objects.dispose();this.renderer.dispose();this.renderer.domElement.remove();
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
  const [environment, setEnvironment] = useState<{ token: string; value: EnvironmentFrame } | null>(null);
  const [error, setError] = useState("");
  const [rendererError, setRendererError] = useState("");
  const [view, setView] = useState<View>("perspective");
  const [representation, setRepresentation] = useState<Representation>("surface");
  const [showBoxes, setShowBoxes] = useState(false);
  const [counts, setCounts] = useState<SceneCounts | null>(null);
  const [renderedToken, setRenderedToken] = useState<string | null>(null);

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
    let active = true;
    queueMicrotask(() => { if (active) { setCounts(null); setError(""); } });
    if (!token) return () => { active = false; };
    void loadEnvironmentFrame(token)
      .then(value => {
        if (!active) return;
        setEnvironment({ token, value });
        setError("");
      })
      .catch(cause => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : "Lỗi tải LiDAR");
        onFrameError?.();
      });
    return () => { active = false; };
  }, [token, onFrameError]);

  useEffect(() => {
    if (!nextToken || nextToken === token) return;
    void loadEnvironmentFrame(nextToken)
      .catch(() => { /* Prefetch failure is retried when the frame becomes current. */ });
  }, [nextToken, token]);

  useEffect(() => {
    if (!token || environment?.token !== token || frame?.frame.sampleToken !== token || !spatial.current) return;
    const result = spatial.current.setData(environment.value.points, frame?.detections ?? []);
    queueMicrotask(() => { setCounts(result); setRenderedToken(token); onFrameReady?.(token); });
  }, [environment, frame, token, onFrameReady]);

  useEffect(() => { spatial.current?.setOptions(representation, showBoxes); }, [representation, showBoxes]);

  const visibleError = rendererError || error || requestError;
  return <section aria-busy={renderedToken !== token && !visibleError} className="relative h-full min-h-0 overflow-hidden bg-[#071720] text-white">
    <div ref={host} className="absolute inset-0" />
    <div className="spatial-readout">
      <p>LIDAR / KHÔNG GIAN 3D</p>
      <span>{environment && environment.token === token ? `${environment.value.points.length.toLocaleString()} điểm · ${frame?.detections.length ?? 0} vật cản` : "Đang tải LiDAR…"}</span>
    </div>
    <div className="spatial-controls">
      <div className="spatial-representation" role="group" aria-label="Cách hiển thị 3D">
        <button type="button" aria-pressed={representation === "surface"} onClick={() => setRepresentation("surface")}>Dựng hình</button>
        <button type="button" aria-pressed={representation === "points"} onClick={() => setRepresentation("points")}>Điểm LiDAR</button>
        <label><input type="checkbox" checked={showBoxes} onChange={event => setShowBoxes(event.target.checked)} />Hộp đo</label>
      </div>
      <div className="spatial-presets" role="group" aria-label="Góc nhìn 3D">
      {([ ["perspective", "Góc 3D"], ["top", "Từ trên"], ["side", "Nhìn ngang"], ["near", "Cận cảnh"] ] as const).map(([value, label]) =>
        <button key={value} type="button" aria-pressed={view === value} onClick={() => { setView(value); spatial.current?.setView(value); }}>{label}</button>)}
      </div>
    </div>
    <div className="spatial-legend">
      <p className="spatial-legend-title">{representation === "surface" ? "HÌNH ĐẠI DIỆN / BỀ MẶT QUAN SÁT" : "ĐIỂM ĐO / LIDAR"}</p><div className="spatial-legend-items">
        {representation === "surface" ? <>
          <p><i style={{ backgroundColor: "#81d2ce" }} />Xe<span>{counts?.cars ?? "—"}</span></p>
          <p><i style={{ backgroundColor: "#ffbf83" }} />Người<span>{counts?.people ?? "—"}</span></p>
          {counts?.others ? <p><i style={{ backgroundColor: "#b6bfbe" }} />Khối khác<span>{counts.others}</span></p> : null}
          <p><i style={{ backgroundColor: "#689b98" }} />Mặt nền</p>
          <p><i style={{ backgroundColor: "#879fae" }} />Mặt dựng<span>{counts?.facades ?? "—"} mảng</span></p>
          <p><i style={{ backgroundColor: "#d9ee98" }} />Xe của bạn</p>
        </> : ([ ["ground", "Mặt thấp"], ["raised", "Bề mặt cao"], ["obstacle", "Trong hộp vật cản"] ] as const).map(([key,label]) => <p key={key}><i style={{backgroundColor:COLORS[key]}} />{label}<span>{counts ? counts[key].toLocaleString() : "—"}</span></p>)}
      </div><p className="spatial-hint">{representation === "surface" ? "Xe/người là hình đại diện theo hộp dự đoán; mặt nền/mặt dựng nội suy từ LiDAR. Vùng khuất chưa biết." : "Kéo để xoay · cuộn để zoom. Vùng trống chưa chắc thông thoáng."}</p>
    </div>
    {visibleError ? <div role="alert" className="absolute inset-0 grid place-items-center bg-[#071720]/90 p-6 text-center text-sm text-rose-300">{visibleError}</div>
      : renderedToken !== token ? <div role="status" className="absolute inset-0 grid place-items-center bg-[#071720]/95 p-6 text-center text-sm text-slate-200">Đang đồng bộ LiDAR và vật cản của frame…</div> : null}
  </section>;
}
