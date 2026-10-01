/**
 * Raw detection payload accepted at the viewer boundary.
 *
 * This mirrors the generated lab API contract without becoming the viewer's
 * internal representation. The shared API client can pass its structurally
 * compatible response here without the viewer owning request state.
 */
export interface DetectionFramePayload {
  frame: {
    sample_token: string;
    sample_idx: number;
    scene: string;
    timestamp_s: number;
    split: "mini_val";
  };
  model: string;
  mode: "precomputed";
  coordinates: Readonly<Record<string, string>>;
  boxes: readonly DetectionBoxPayload[];
}

export interface DetectionBoxPayload {
  class_name: string;
  x: number;
  y: number;
  z: number;
  w: number;
  l: number;
  h: number;
  yaw: number;
  vx: number;
  vy: number;
  score: number;
}

export interface EgoPoint {
  /** +forward, in metres. */
  forward: number;
  /** +left, in metres. */
  left: number;
  /** +up, in metres. */
  up: number;
}

export interface EgoVelocity {
  /** Velocity toward ego-forward, in metres per second. */
  forward: number;
  /** Velocity toward ego-left, in metres per second. */
  left: number;
}

export interface DetectionSize {
  width: number;
  length: number;
  height: number;
}

export interface ViewerDetection {
  id: string;
  className: string;
  center: EgoPoint;
  size: DetectionSize;
  /** Counterclockwise from ego-forward toward ego-left. */
  yawRadians: number;
  velocity: EgoVelocity;
  confidence: number;
}

export interface ViewerFrameMetadata {
  sampleToken: string;
  sampleIndex: number;
  sceneId: string;
  timestampSeconds: number;
  split: "mini_val";
}

export interface ViewerDetectionFrame {
  frame: ViewerFrameMetadata;
  modelId: string;
  sourceMode: "precomputed";
  sourceCoordinates: Readonly<Record<string, string>>;
  detections: readonly ViewerDetection[];
}

/** Renderer-independent pan and zoom state, suitable for controlled syncing. */
export interface BevViewState {
  center: {
    forward: number;
    left: number;
  };
  /** Orthographic span along the viewport's vertical axis, in metres. */
  visibleHeightMeters: number;
}

export interface BevLayerVisibility {
  detections: boolean;
  confidence: boolean;
  grid: boolean;
  egoMarker: boolean;
}

/** Display-only dimensions derived from the camera zoom and container aspect. */
export interface BevViewportMetrics {
  visibleWidthMeters: number;
  visibleHeightMeters: number;
  gridSpacingMeters: number;
}
