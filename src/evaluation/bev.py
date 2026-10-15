import numpy as np


class BevEvaluator:
    def __init__(self):
        self.confusion = np.zeros((3, 3), dtype=np.int64)
        self.flow_error = 0.0
        self.flow_count = 0
        self.frames = 0

    def add(self, frame, prediction):
        gt, pred, mask = frame["labels"], prediction["occupancy"], frame["valid"]
        self.confusion += np.bincount((gt[mask] * 3 + pred[mask]).astype(int), minlength=9).reshape(3, 3)
        if prediction["flow"] is not None:
            valid = frame["flow_valid"]
            error = np.linalg.norm(prediction["flow"] - frame["flow"], axis=0)
            self.flow_error += float(error[valid].sum())
            self.flow_count += int(valid.sum())
        self.frames += 1

    def report(self, timing):
        cm = self.confusion
        intersection = np.diag(cm)
        union = cm.sum(axis=0) + cm.sum(axis=1) - intersection
        per_class = [float(intersection[i] / union[i]) if union[i] else None for i in range(3)]
        occupied_tp = int(cm[1:, 1:].sum())
        occupied_union = int(cm[1:, :].sum() + cm[:, 1:].sum() - occupied_tp)
        supported = [v for v in per_class if v is not None]
        return {
            "frame_count": self.frames,
            "evaluated_cells": int(cm.sum()),
            "confusion": cm.tolist(),
            "class_iou": dict(zip(("free", "static", "object"), per_class, strict=True)),
            "miou_supported_classes": float(np.mean(supported)) if supported else None,
            "occupied_iou": occupied_tp / occupied_union if occupied_union else None,
            "object_recall": float(cm[2, 2] / cm[2].sum()) if cm[2].sum() else None,
            "flow_epe_m_s": self.flow_error / self.flow_count if self.flow_count else None,
            "flow_valid_cells": self.flow_count,
            "latency_model_only_ms": {"p50": float(np.percentile(timing, 50)), "p95": float(np.percentile(timing, 95))}
            if timing
            else None,
            "timed_frames": len(timing),
        }


def recommend(results, max_latency_ms=None):
    eligible = [
        (name, result)
        for name, result in results.items()
        if result["metrics"]["occupied_iou"] is not None
        and (
            max_latency_ms is None
            or (
                result["metrics"]["latency_model_only_ms"] is not None
                and result["metrics"]["latency_model_only_ms"]["p95"] <= max_latency_ms
            )
        )
    ]
    eligible.sort(key=lambda pair: (-pair[1]["metrics"]["occupied_iou"], pair[0]))
    return {
        "criterion": "occupied_iou descending; optional measured p95 latency constraint",
        "ranking": [name for name, _ in eligible],
        "selected": eligible[0][0] if eligible else None,
        "limitations": [
            "Selection applies to this capture and BEV occupancy only; not a detection model recommendation",
            "No claim of generalization to real driving; separate held-out routes/scenes required",
            "Flow checkpoints are ranked by occupancy, not by flow quality",
        ],
    }
