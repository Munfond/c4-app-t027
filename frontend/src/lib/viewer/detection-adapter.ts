import type {
  DetectionBoxPayload,
  DetectionFramePayload,
  ViewerDetection,
  ViewerDetectionFrame,
} from "./types";

function adaptDetection(
  box: DetectionBoxPayload,
  frameIdentity: string,
  index: number,
): ViewerDetection {
  return {
    id: `${frameIdentity}:${index}`,
    className: box.class_name,
    center: {
      forward: box.x,
      left: box.y,
      up: box.z,
    },
    size: {
      width: box.w,
      length: box.l,
      height: box.h,
    },
    yawRadians: box.yaw,
    velocity: {
      forward: box.vx,
      left: box.vy,
    },
    confidence: box.score,
  };
}

/**
 * Converts the API-shaped payload exactly once at the viewer boundary.
 * Scores are preserved as returned because thresholding belongs to the API.
 */
export function adaptDetectionFrame(
  payload: DetectionFramePayload,
): ViewerDetectionFrame {
  const frameIdentity = `${payload.frame.sample_token}:${payload.model}`;

  return {
    frame: {
      sampleToken: payload.frame.sample_token,
      sampleIndex: payload.frame.sample_idx,
      sceneId: payload.frame.scene,
      timestampSeconds: payload.frame.timestamp_s,
      split: payload.frame.split,
    },
    modelId: payload.model,
    sourceMode: payload.mode,
    sourceCoordinates: { ...payload.coordinates },
    detections: payload.boxes.map((box, index) =>
      adaptDetection(box, frameIdentity, index),
    ),
  };
}
