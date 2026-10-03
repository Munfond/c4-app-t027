"""Generate all demo media (81 frames: cameras + environment) for cloud deployment.
Optimizes camera images to ~35KB JPEG so the entire 486-camera cache is < 20MB.
"""

import json
from pathlib import Path
from PIL import Image

from src.services import lab
from src.services.environment import build_environment

def main():
    settings = lab.get_settings()
    frames = lab.frames()
    print(f"Total frames to process: {len(frames)}")

    cam_dir = settings.lab_data_root / "cache/cameras"
    cam_dir.mkdir(parents=True, exist_ok=True)
    env_dir = settings.lab_data_root / "cache/environment"
    env_dir.mkdir(parents=True, exist_ok=True)

    cam_count = 0
    env_count = 0

    for idx, f in enumerate(frames, 1):
        token = f["sample_token"]

        # 1. Environment pointcloud
        env_file = env_dir / f"{token}.json"
        if not env_file.is_file():
            env_data = build_environment(token)
            env_file.write_text(json.dumps(env_data, separators=(",", ":")))
            env_count += 1

        # 2. Six Cameras
        for ch in lab.CAMERAS:
            cam_file = cam_dir / f"{token}_{ch}.jpg"
            if not cam_file.is_file():
                raw_path = lab.camera_path(token, ch)
                with Image.open(raw_path) as im:
                    im.thumbnail((800, 600))
                    im.save(cam_file, format="JPEG", quality=75, optimize=True)
                cam_count += 1

        if idx % 10 == 0 or idx == len(frames):
            print(f"[{idx}/{len(frames)}] Processed frames... (new cameras: {cam_count}, new envs: {env_count})")

    total_cams = len(list(cam_dir.glob("*.jpg")))
    total_envs = len(list(env_dir.glob("*.json")))
    print(f"\n[DONE] Cameras: {total_cams}/486, Environments: {total_envs}/81")

if __name__ == "__main__":
    main()
