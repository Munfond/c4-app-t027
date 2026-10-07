"""Image transforms and optional local post-NMS ONNX detector, no weight downloads."""

import hashlib
import io
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from src.config import get_settings


def weather_image(image, weather, strength, rng):
    if weather == "fog":
        return Image.blend(image, Image.new("RGB", image.size, (220, 225, 230)), strength)
    if weather == "rain":
        image = Image.blend(image, Image.new("RGB", image.size, (40, 45, 50)), strength * 0.3)
        layer = Image.new("RGB", image.size, (0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for _ in range(int(image.width * image.height * strength / 250)):
            x, y = rng.integers(0, image.width), rng.integers(0, image.height)
            draw.line((int(x), int(y), int(x + 3), int(y + 14)), fill=(180, 185, 190), width=1)
        return Image.blend(image, Image.fromarray(np.maximum(np.asarray(image), np.asarray(layer))), strength)
    return image.copy()


def camera_variant(reference, spec):
    size = (max(1, round(reference.width * spec.scale)), max(1, round(reference.height * spec.scale)))
    reduced = reference.resize(size, Image.Resampling.LANCZOS)
    if spec.blur_radius:
        reduced = reduced.filter(ImageFilter.GaussianBlur(spec.blur_radius))
    buffer = io.BytesIO()
    reduced.save(buffer, format="JPEG", quality=spec.jpeg_quality)
    payload = buffer.getvalue()
    with Image.open(io.BytesIO(payload)) as encoded:
        decoded = encoded.convert("RGB")
    reconstructed = decoded.resize(reference.size, Image.Resampling.BILINEAR)
    mse = float(np.mean((np.asarray(reference, dtype=float) - np.asarray(reconstructed, dtype=float)) ** 2))
    return decoded, payload, {
        "width": size[0], "height": size[1], "encoded_bytes": len(payload),
        "psnr_db": min(100.0, 10 * np.log10(255**2 / max(mse, 1e-8))),
        "reference_exact": mse == 0,
    }


def detection_retention(reference, candidate, threshold=0.5):
    """Greedy one-to-one same-class IoU recall against baseline predictions, NOT ground truth."""
    used, matched = set(), 0
    for box in sorted(reference, key=lambda b: -b[4]):
        eligible = []
        for index, other in enumerate(candidate):
            if index in used or box[5] != other[5]:
                continue
            wh = np.maximum(0, np.minimum(box[2:4], other[2:4]) - np.maximum(box[:2], other[:2]))
            intersection = float(np.prod(wh))
            area = np.prod(np.maximum(0, box[2:4] - box[:2])) + np.prod(np.maximum(0, other[2:4] - other[:2]))
            iou = intersection / max(float(area - intersection), 1e-8)
            eligible.append((iou, index))
        if eligible and max(eligible)[0] >= threshold:
            used.add(max(eligible)[1])
            matched += 1
    return matched / len(reference) if len(reference) else None


class CameraDetector:
    """Contract: float32 RGB NCHW [1,3,H,W], output [N,6] or [1,N,6].

    Post-NMS rows x1,y1,x2,y2,score,class in resized-input pixel coordinates.
    Raw YOLO/fusion exports require an explicit postprocessing export first.
    """

    def __init__(self):
        settings = get_settings()
        self.path = settings.replay_camera_onnx
        self.session = None
        self.digest = None
        self.timing = []
        self.size = settings.replay_camera_input_size
        self.threshold = settings.replay_camera_score_threshold
        if self.path:
            import onnxruntime as ort

            with self.path.open("rb") as stream:
                self.digest = hashlib.file_digest(stream, "sha256").hexdigest()
            self.session = ort.InferenceSession(str(self.path), providers=["CPUExecutionProvider"])
            if len(self.session.get_inputs()) != 1:
                raise ValueError("Camera ONNX must have one RGB image input")
            shape = self.session.get_inputs()[0].shape
            if len(shape) != 4 or shape[1] != 3 or shape[0] not in (1, None, "batch", "batch_size"):
                raise ValueError("Camera ONNX input must be RGB NCHW with batch 1")
            self.height = shape[2] if isinstance(shape[2], int) else self.size
            self.width = shape[3] if isinstance(shape[3], int) else self.size
            if len(shape) != 4 or shape[1] != 3 or not (1 <= self.width <= 2048 and 1 <= self.height <= 2048):
                raise ValueError("Camera ONNX input must be RGB NCHW, max 2048 pixels/axis")

    def predict(self, image):
        if self.session is None:
            return None
        tensor = np.asarray(image.resize((self.width, self.height)), dtype=np.float32).transpose(2, 0, 1)[None] / 255
        start = time.perf_counter()
        output = np.asarray(self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0])
        self.timing.append((time.perf_counter() - start) * 1000)
        if output.ndim == 3 and output.shape[0] == 1:
            output = output[0]
        if output.ndim != 2 or output.shape[1] != 6 or not np.isfinite(output).all():
            raise ValueError("Camera ONNX output must be finite post-NMS [N,6] xyxy/score/class")
        boxes = output[output[:, 4] >= self.threshold].astype(float)
        if np.any(boxes[:, 4] > 1) or np.any(boxes[:, 5] < 0) or np.any(boxes[:, 5] != np.floor(boxes[:, 5])):
            raise ValueError("Camera ONNX scores must be <=1 and class IDs nonnegative integers")
        if len(boxes) > 1000:
            raise ValueError("Camera ONNX output exceeds 1000 detections")
        boxes[:, [0, 2]] *= image.width / self.width
        boxes[:, [1, 3]] *= image.height / self.height
        return boxes.tolist()
