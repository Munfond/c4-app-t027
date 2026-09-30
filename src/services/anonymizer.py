"""Optional, lazy image anonymization. Never return an unprocessed fallback."""

import io
import logging
from threading import Lock

from PIL import Image, UnidentifiedImageError

from src.config import get_settings

logger = logging.getLogger(__name__)
_lock = Lock()
_service = None


class InvalidImageError(ValueError):
    pass


class UnavailableAnonymizerError(RuntimeError):
    pass


class AnonymizerService:
    def __init__(self):
        import torch
        from facenet_pytorch import MTCNN
        from ultralytics import YOLO

        weights = get_settings().plate_weights
        if not weights.is_file():
            raise UnavailableAnonymizerError("Plate weights missing")
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.mtcnn = MTCNN(keep_all=True, device=device)
        self.plate_model = YOLO(str(weights))

    @staticmethod
    def _apply_blur(image, box):
        import cv2

        x1, y1, x2, y2 = map(int, box)
        h, w = image.shape[:2]
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
        roi = image[y1:y2, x1:x2]
        if roi.size:
            kw = max(15, (roi.shape[1] // 3) | 1)
            kh = max(15, (roi.shape[0] // 3) | 1)
            image[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (kw, kh), 30)
        return image

    def anonymize_frame(self, frame):
        import cv2

        output = frame.copy()
        boxes, _ = self.mtcnn.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if boxes is not None:
            for box in boxes:
                self._apply_blur(output, box)
        for result in self.plate_model.predict(source=frame, conf=0.15, verbose=False):
            for box in result.boxes:
                self._apply_blur(output, box.xyxy[0].cpu().numpy())
        return output


def anonymize_bytes(contents: bytes) -> bytes:
    global _service
    settings = get_settings()
    try:
        with Image.open(io.BytesIO(contents)) as image:
            if image.format not in {"JPEG", "PNG"} or image.width * image.height > settings.max_image_pixels:
                raise InvalidImageError("Unsupported image or excessive dimensions")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Invalid image") from exc
    if not settings.anonymizer_enabled:
        raise UnavailableAnonymizerError("Disabled")
    with _lock:
        try:
            import cv2
            import numpy as np

            if _service is None:
                _service = AnonymizerService()
            frame = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise InvalidImageError("Invalid image")
            ok, encoded = cv2.imencode(".jpg", _service.anonymize_frame(frame))
            if not ok:
                raise UnavailableAnonymizerError("Encoding failed")
            return encoded.tobytes()
        except InvalidImageError:
            raise
        except Exception as exc:
            logger.exception("Anonymization failed")
            raise UnavailableAnonymizerError("Processing failed") from exc
