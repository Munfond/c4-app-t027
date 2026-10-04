import { centreDistance, proximityColor } from "./proximity";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import {
  BEV_BASE_FRUSTUM_HEIGHT_METERS,
  bevCenterToWorldTarget,
  cameraZoomToVisibleHeight,
  detectionToBevBoxTransform,
  getBevViewportExtent,
  getOrthographicFrustum,
  visibleHeightToCameraZoom,
  worldTargetToBevCenter,
} from "@/lib/geometry";

import type {
  BevLayerVisibility,
  BevViewportMetrics,
  BevViewState,
  ViewerDetection,
} from "./types";
import {
  areBevViewStatesEquivalent,
  BEV_VIEW_BOUNDS,
  constrainBevViewState,
  DEFAULT_BEV_VIEW_STATE,
} from "./view-state";

const CAMERA_HEIGHT_METERS = 500;
const GRID_SIZE_METERS = 2_000;
const GRID_DIVISIONS = 200;
const GRID_SPACING_METERS = GRID_SIZE_METERS / GRID_DIVISIONS;

export interface BevRendererOptions {
  ariaLabel: string;
  initialViewState?: BevViewState;
  onViewStateChange?: (viewState: BevViewState) => void;
  onSelectDetection?: (id: string) => void;
  onViewportMetricsChange?: (metrics: BevViewportMetrics) => void;
}

function disposeMaterial(material: THREE.Material): void {
  const texturedMaterial = material as THREE.Material & {
    map?: THREE.Texture | null;
  };
  texturedMaterial.map?.dispose();
  material.dispose();
}

function disposeObject(root: THREE.Object3D): void {
  root.traverse((object) => {
    const renderable = object as THREE.Object3D & {
      geometry?: THREE.BufferGeometry;
      material?: THREE.Material | THREE.Material[];
    };

    renderable.geometry?.dispose();
    if (Array.isArray(renderable.material)) {
      renderable.material.forEach(disposeMaterial);
    } else if (renderable.material) {
      disposeMaterial(renderable.material);
    }
  });
}

interface TextSprite {
  canvas: HTMLCanvasElement;
  context: CanvasRenderingContext2D;
  sprite: THREE.Sprite;
  texture: THREE.CanvasTexture;
  text: string;
  color: string;
}

interface DetectionVisual {
  box: THREE.Group;
  fillMaterial: THREE.MeshBasicMaterial;
  edgeMaterial: THREE.LineBasicMaterial;
  confidence: TextSprite | null;
}

function drawTextSprite(
  canvas: HTMLCanvasElement,
  context: CanvasRenderingContext2D,
  text: string,
  color: string,
): void {
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "rgba(9, 9, 11, 0.88)";
  context.beginPath();
  context.roundRect(4, 4, canvas.width - 8, canvas.height - 8, 18);
  context.fill();
  context.strokeStyle = color;
  context.lineWidth = 5;
  context.stroke();
  context.font = "600 30px system-ui, sans-serif";
  context.fillStyle = "#fafafa";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(text, canvas.width / 2, canvas.height / 2, canvas.width - 28);
}

function createTextSprite(text: string, color: string): TextSprite | null {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 96;

  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  drawTextSprite(canvas, context, text, color);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;

  let material: THREE.SpriteMaterial | null = null;
  try {
    material = new THREE.SpriteMaterial({
      map: texture,
      depthTest: false,
      depthWrite: false,
      transparent: true,
    });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(4.5, 1.1, 1);
    sprite.renderOrder = 20;
    return { canvas, context, sprite, texture, text, color };
  } catch (cause) {
    material?.dispose();
    texture.dispose();
    throw cause;
  }
}

function updateTextSprite(
  textSprite: TextSprite,
  text: string,
  color: string,
): void {
  if (textSprite.text === text && textSprite.color === color) {
    return;
  }

  drawTextSprite(textSprite.canvas, textSprite.context, text, color);
  textSprite.texture.needsUpdate = true;
  textSprite.text = text;
  textSprite.color = color;
}

function createEgoMarker(): THREE.Group {
  const group = new THREE.Group();
  group.name = "ego-marker";

  const bodyGeometry = new THREE.BoxGeometry(1.9, 0.8, 4.5);
  const bodyMaterial = new THREE.MeshBasicMaterial({
    color: "#e4e4e7",
    opacity: 0.2,
    transparent: true,
  });
  const body = new THREE.Mesh(bodyGeometry, bodyMaterial);
  body.position.y = 0.4;
  group.add(body);

  const outlineGeometry = new THREE.EdgesGeometry(bodyGeometry);
  const outlineMaterial = new THREE.LineBasicMaterial({ color: "#f4f4f5" });
  const outline = new THREE.LineSegments(outlineGeometry, outlineMaterial);
  outline.position.copy(body.position);
  group.add(outline);

  const direction = new THREE.ArrowHelper(
    new THREE.Vector3(0, 0, -1),
    new THREE.Vector3(0, 0.9, -2.4),
    5,
    "#22d3ee",
    1.1,
    0.65,
  );
  group.add(direction);

  return group;
}

function updateDetectionVisual(
  visual: DetectionVisual,
  detection: ViewerDetection,
): void {
  const transform = detectionToBevBoxTransform(detection);
  const color = proximityColor(detection);
  visual.box.name = `detection:${detection.id}`;
  visual.box.userData.detectionId = detection.id;
  visual.box.position.set(
    transform.position.x,
    transform.position.y,
    transform.position.z,
  );
  visual.box.rotation.y = transform.rotationYRadians;
  visual.box.scale.set(transform.size.x, transform.size.y, transform.size.z);
  visual.box.visible = true;
  visual.fillMaterial.color.set(color);
  visual.edgeMaterial.color.set(color);

  if (visual.confidence) {
    updateTextSprite(
      visual.confidence,
      `${centreDistance(detection).toFixed(1)} m`,
      color,
    );
    visual.confidence.sprite.position.set(
      transform.position.x,
      transform.position.y + transform.size.y / 2 + 1.5,
      transform.position.z,
    );
    visual.confidence.sprite.visible = true;
  }
}

function createDetectionVisual(
  detection: ViewerDetection,
): DetectionVisual {
  const color = proximityColor(detection);
  const group = new THREE.Group();

  const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  const fillMaterial = new THREE.MeshBasicMaterial({
    color,
    depthWrite: false,
    opacity: 0.42,
    transparent: true,
  });
  const fill = new THREE.Mesh(boxGeometry, fillMaterial);
  fill.renderOrder = 2;
  group.add(fill);

  const edgeGeometry = new THREE.EdgesGeometry(boxGeometry);
  const edgeMaterial = new THREE.LineBasicMaterial({ color });
  const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
  edges.renderOrder = 3;
  group.add(edges);

  let confidence: TextSprite | null = null;
  try {
    confidence = createTextSprite(
      `${centreDistance(detection).toFixed(1)} m`,
      color,
    );
    const visual: DetectionVisual = {
      box: group,
      fillMaterial,
      edgeMaterial,
      confidence,
    };
    updateDetectionVisual(visual, detection);
    return visual;
  } catch (cause) {
    if (confidence) {
      disposeObject(confidence.sprite);
    }
    disposeObject(group);
    throw cause;
  }
}

export class BevRenderer {
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.OrthographicCamera;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly controls: OrbitControls;
  private readonly grid: THREE.GridHelper;
  private readonly egoMarker: THREE.Group;
  private readonly resizeObserver: ResizeObserver;
  private readonly detectionsGroup = new THREE.Group();
  private readonly confidenceGroup = new THREE.Group();
  private environmentPoints: THREE.Points | null = null;
  private readonly detectionPool: DetectionVisual[] = [];
  private pointerStart: {x: number; y: number} | null = null;
  private animationFrame: number | null = null;
  private viewportAspect = 1;
  private applyingViewState = false;
  private disposed = false;

  constructor(
    private readonly container: HTMLElement,
    private readonly options: BevRendererOptions,
  ) {
    this.camera = new THREE.OrthographicCamera(-50, 50, 50, -50, 0.1, 2_000);
    this.camera.up.set(0, 0, -1);
    this.camera.position.set(0, CAMERA_HEIGHT_METERS, 0);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    this.renderer.setClearColor(0x0b2028, 1);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.setAttribute("aria-label", options.ariaLabel);
    this.renderer.domElement.setAttribute("role", "application");
    this.renderer.domElement.style.display = "block";
    this.renderer.domElement.style.height = "100%";
    this.renderer.domElement.style.width = "100%";
    this.container.appendChild(this.renderer.domElement);
    this.renderer.domElement.addEventListener("pointerdown", this.handlePointerDown);
    this.renderer.domElement.addEventListener("pointerup", this.handlePointerUp);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.enableRotate = false;
    this.controls.screenSpacePanning = true;
    this.controls.minZoom =
      BEV_BASE_FRUSTUM_HEIGHT_METERS /
      BEV_VIEW_BOUNDS.maxVisibleHeightMeters;
    this.controls.maxZoom =
      BEV_BASE_FRUSTUM_HEIGHT_METERS /
      BEV_VIEW_BOUNDS.minVisibleHeightMeters;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
    this.controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    this.controls.touches.ONE = THREE.TOUCH.PAN;
    this.controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
    this.controls.addEventListener("change", this.handleControlsChange);

    this.grid = new THREE.GridHelper(
      GRID_SIZE_METERS,
      GRID_DIVISIONS,
      "#26444c",
      "#17323b",
    );
    this.grid.position.y = -0.05;
    this.grid.name = "metric-grid-10m";
    this.scene.add(this.grid);

    this.egoMarker = createEgoMarker();
    this.scene.add(this.egoMarker);
    for (const radius of [10, 25, 50]) {
      const points = Array.from({ length: 129 }, (_, i) => {
        const angle = i / 128 * Math.PI * 2;
        return new THREE.Vector3(Math.cos(angle) * radius, 0.02, Math.sin(angle) * radius);
      });
      const ring = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({ color: "#4c7a82", transparent: true, opacity: 0.5 }));
      this.scene.add(ring);
    }
    this.scene.add(this.detectionsGroup, this.confidenceGroup);

    this.setViewState(options.initialViewState ?? DEFAULT_BEV_VIEW_STATE);

    this.resizeObserver = new ResizeObserver(this.handleResize);
    this.resizeObserver.observe(this.container);
    this.resize();
  }

  setDetections(detections: readonly ViewerDetection[]): void {
    detections.forEach((detection, index) => {
      let visual = this.detectionPool[index];
      if (!visual) {
        visual = createDetectionVisual(detection);
        this.detectionPool.push(visual);
        this.detectionsGroup.add(visual.box);
        if (visual.confidence) {
          this.confidenceGroup.add(visual.confidence.sprite);
        }
      } else {
        updateDetectionVisual(visual, detection);
      }
    });

    for (
      let index = detections.length;
      index < this.detectionPool.length;
      index += 1
    ) {
      const visual = this.detectionPool[index];
      visual.box.visible = false;
      if (visual.confidence) {
        visual.confidence.sprite.visible = false;
      }
    }

    this.scheduleRender();
  }

  setSelectedDetection(id: string | null): void {
    for (const visual of this.detectionPool) {
      visual.edgeMaterial.color.copy(visual.fillMaterial.color);
      if (visual.box.name === `detection:${id}`) visual.edgeMaterial.color.set("#ffffff");
    }
    this.scheduleRender();
  }

  setEnvironment(points: readonly number[][]): void {
    if (this.environmentPoints) {
      this.scene.remove(this.environmentPoints);
      disposeObject(this.environmentPoints);
    }
    const positions = new Float32Array(points.length * 3);
    const colors = new Float32Array(points.length * 3);
    const raisedColor = new THREE.Color("#91b9c2");
    const groundColor = new THREE.Color("#31515b");
    for (let index = 0; index < points.length; index++) {
      const [forward, left, up] = points[index];
      const offset = index * 3;
      positions[offset] = -left;
      positions[offset + 1] = -0.02;
      positions[offset + 2] = -forward;
      const color = up > 0.4 ? raisedColor : groundColor;
      colors[offset] = color.r;
      colors[offset + 1] = color.g;
      colors[offset + 2] = color.b;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    this.environmentPoints = new THREE.Points(geometry, new THREE.PointsMaterial({
      size: 2, sizeAttenuation: false, vertexColors: true, depthWrite: false,
    }));
    this.scene.add(this.environmentPoints);
    this.scheduleRender();
  }

  setLayers(layers: BevLayerVisibility): void {
    this.detectionsGroup.visible = layers.detections;
    this.confidenceGroup.visible = layers.detections && layers.confidence;
    this.grid.visible = layers.grid;
    this.egoMarker.visible = layers.egoMarker;
    this.scheduleRender();
  }

  setAriaLabel(ariaLabel: string): void {
    this.renderer.domElement.setAttribute("aria-label", ariaLabel);
  }

  setViewState(nextViewState: BevViewState): void {
    const viewState = constrainBevViewState(nextViewState);
    if (areBevViewStatesEquivalent(this.getViewState(), viewState)) {
      return;
    }

    this.applyingViewState = true;
    const target = bevCenterToWorldTarget(viewState.center);
    this.controls.target.set(target.x, 0, target.z);
    this.camera.position.set(target.x, CAMERA_HEIGHT_METERS, target.z);
    this.camera.zoom = visibleHeightToCameraZoom(
      viewState.visibleHeightMeters,
    );
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.applyingViewState = false;
    this.scheduleRender();
    this.emitViewportMetrics();
  }

  getViewState(): BevViewState {
    return constrainBevViewState({
      center: worldTargetToBevCenter(this.controls.target),
      visibleHeightMeters: cameraZoomToVisibleHeight(this.camera.zoom),
    });
  }

  getViewportMetrics(): BevViewportMetrics {
    const extent = getBevViewportExtent(
      cameraZoomToVisibleHeight(this.camera.zoom),
      this.viewportAspect,
    );

    return {
      visibleWidthMeters: extent.widthMeters,
      visibleHeightMeters: extent.heightMeters,
      gridSpacingMeters: GRID_SPACING_METERS,
    };
  }

  dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;

    this.resizeObserver.disconnect();
    this.controls.removeEventListener("change", this.handleControlsChange);
    this.controls.dispose();
    this.renderer.domElement.removeEventListener("pointerdown", this.handlePointerDown);
    this.renderer.domElement.removeEventListener("pointerup", this.handlePointerUp);
    if (this.animationFrame !== null) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }

    disposeObject(this.scene);
    this.scene.clear();
    this.detectionPool.length = 0;
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
  }

  private readonly handlePointerDown = (event: PointerEvent): void => {
    this.pointerStart = { x: event.clientX, y: event.clientY };
  };

  private readonly handlePointerUp = (event: PointerEvent): void => {
    if (!this.pointerStart || Math.hypot(event.clientX - this.pointerStart.x, event.clientY - this.pointerStart.y) > 5) return;
    this.pointerStart = null;
    if (!this.detectionsGroup.visible) return;
    const bounds = this.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2((event.clientX-bounds.left)/bounds.width*2-1, 1-(event.clientY-bounds.top)/bounds.height*2);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(pointer, this.camera);
    const boxes = this.detectionsGroup.children.filter(box => box.visible);
    const hit = raycaster.intersectObjects(boxes, true)[0];
    const id = hit?.object.parent?.userData.detectionId;
    if (typeof id === "string") this.options.onSelectDetection?.(id);
  };

  private readonly handleControlsChange = (): void => {
    this.scheduleRender();
    this.emitViewportMetrics();
    if (!this.applyingViewState) {
      this.options.onViewStateChange?.(this.getViewState());
    }
  };

  private readonly handleResize = (): void => {
    this.resize();
  };

  private resize(): void {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width <= 0 || height <= 0) {
      return;
    }

    const aspect = width / height;
    const frustum = getOrthographicFrustum(aspect);
    this.viewportAspect = aspect;
    this.camera.left = frustum.left;
    this.camera.right = frustum.right;
    this.camera.top = frustum.top;
    this.camera.bottom = frustum.bottom;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(width, height, false);
    this.scheduleRender();
    this.emitViewportMetrics();
  }

  private emitViewportMetrics(): void {
    this.options.onViewportMetricsChange?.(this.getViewportMetrics());
  }

  private scheduleRender(): void {
    if (this.disposed || this.animationFrame !== null) {
      return;
    }

    this.animationFrame = requestAnimationFrame(() => {
      this.animationFrame = null;
      if (!this.disposed) {
        this.renderer.render(this.scene, this.camera);
      }
    });
  }
}
