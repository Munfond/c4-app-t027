"""Frame barrier reusable by a future ROS bridge. It never silently reuses old data."""
from __future__ import annotations

import time


class FrameBarrier:
    def __init__(self, frame_id: int, topics: set[str], timeout_s: float = 1.0):
        if not topics or timeout_s <= 0:
            raise ValueError("Topics and positive timeout required")
        self.frame_id = frame_id
        self.topics = frozenset(topics)
        self.payloads = {}
        self.deadline = time.monotonic() + timeout_s

    def push(self, topic: str, frame_id: int, payload: object) -> bool:
        if time.monotonic() > self.deadline:
            raise TimeoutError(f"Timed out waiting for frame {self.frame_id}")
        if topic not in self.topics:
            raise ValueError(f"Unexpected topic {topic}")
        if frame_id != self.frame_id:
            return False
        if topic in self.payloads:
            raise ValueError(f"Duplicate topic {topic} for frame {frame_id}")
        self.payloads[topic] = payload
        return True

    def collect(self) -> dict[str, object]:
        if set(self.payloads) == self.topics:
            return dict(self.payloads)
        if time.monotonic() > self.deadline:
            raise TimeoutError(f"Missing topics: {sorted(self.topics - self.payloads.keys())}")
        raise LookupError("Frame is not complete")
