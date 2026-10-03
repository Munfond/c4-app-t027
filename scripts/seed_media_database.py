"""Seed precomputed camera images and LiDAR environments directly into Supabase PostgreSQL.
This completely removes the need to store media files in Git or Docker.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.database import Base, engine, SessionLocal
from src.models.db_models import CameraImageDB, EnvironmentDB
from src.config import get_settings

def main():
    settings = get_settings()
    print("Creating tables in database if not exist...")
    Base.metadata.create_all(bind=engine)

    cam_dir = settings.lab_data_root / "cache/cameras"
    env_dir = settings.lab_data_root / "cache/environment"

    session = SessionLocal()
    try:
        # 1. Seed Environments (81 frames)
        env_files = list(env_dir.glob("*.json"))
        print(f"Found {len(env_files)} environment files to seed...")
        for idx, f in enumerate(env_files, 1):
            token = f.stem
            existing = session.query(EnvironmentDB).filter(EnvironmentDB.sample_token == token).first()
            if not existing:
                content = f.read_text(encoding="utf-8")
                session.add(EnvironmentDB(sample_token=token, payload_json=content))
            if idx % 20 == 0 or idx == len(env_files):
                session.commit()
                print(f"  [Environment] Seeded {idx}/{len(env_files)}")

        # 2. Seed Camera Images (486 images)
        cam_files = [f for f in cam_dir.glob("*.jpg") if f.name != "token-a_CAM_FRONT.jpg"]
        print(f"Clearing any old camera rows and seeding {len(cam_files)} cameras...")
        session.query(CameraImageDB).delete()
        session.commit()

        for idx, f in enumerate(cam_files, 1):
            stem = f.stem
            if len(stem) < 34 or stem[32] != "_":
                continue
            token = stem[:32]
            channel = stem[33:]
            img_bytes = f.read_bytes()
            session.add(CameraImageDB(sample_token=token, channel=channel, image_data=img_bytes))
            if idx % 50 == 0 or idx == len(cam_files):
                session.commit()
                print(f"  [Cameras] Seeded {idx}/{len(cam_files)}")

        session.commit()
        print("\n[SUCCESS] All environments and camera images seeded to Database!")
    finally:
        session.close()

if __name__ == "__main__":
    main()
