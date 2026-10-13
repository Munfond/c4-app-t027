"""Bounded read-only preflight for the manual UI, not a worker-readiness claim."""

import sys
import threading
import time

from src.config import get_settings
from src.simulation.carla_server import require_memory_headroom, require_nvidia_health

_lock = threading.Lock()
_cached = None
_expires = 0.0


def probe():
    settings = get_settings()
    minimum = settings.carla_min_available_memory_gib
    if not settings.carla_server_executable or sys.platform != "linux":
        return {
            "managed": False,
            "hardware_ready": None,
            "notice": "Máy này chưa có runtime CARLA Linux do Lab quản lý. Xem bản ghi vẫn dùng được; capture mới cần server và worker phù hợp.",
        }
    gpu_ok = False
    try:
        require_nvidia_health()
        gpu_ok = True
    except RuntimeError:
        pass
    available = None
    try:
        available = require_memory_headroom(0)
    except (OSError, ValueError, KeyError):
        pass
    memory_ok = available is not None and available >= minimum
    server_ok = settings.carla_server_executable.is_file()
    ready = gpu_ok and memory_ok and server_ok
    if not gpu_ok:
        notice = "GPU NVIDIA chưa sẵn sàng. Kiểm tra nvidia-smi trước khi tạo capture; bạn vẫn xem được bản ghi đã có."
    elif not memory_ok:
        notice = (
            f"Chưa đủ RAM để bắt đầu capture mới: cần {minimum:g} GiB khả dụng. Đóng bớt ứng dụng rồi kiểm tra lại."
        )
    elif not server_ok:
        notice = "Thiếu chương trình CARLA server. Bạn vẫn xem được bản ghi đã có."
    else:
        notice = (
            "GPU và RAM đạt preflight. Capture mới vẫn cần worker chạy; không bảo đảm mọi cấu hình đều phù hợp với máy."
        )
    return {
        "managed": True,
        "hardware_ready": ready,
        "gpu_ready": gpu_ok,
        "memory_available_gib": round(available, 1) if available is not None else None,
        "memory_required_gib": minimum,
        "server_present": server_ok,
        "notice": notice,
    }


def snapshot():
    global _cached, _expires
    with _lock:
        if _cached is None or time.monotonic() >= _expires:
            _cached = probe()
            _expires = time.monotonic() + 12
        return _cached
