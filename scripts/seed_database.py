#!/usr/bin/env python3
"""
Seed script to migrate Lab data from CSV files into Database (PostgreSQL / SQLite).
Safe and idempotent.
"""

import csv
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings
from src.database import Base, SessionLocal, engine
from src.models.db_models import BenchmarkDB, BenchmarkReportDB, DetectionDB, FrameDB
from src.services.lab import DETECTORS


def seed_frames(db, lab_root: Path):
    samples_csv = lab_root / "exports/L3E/samples.csv"
    if not samples_csv.is_file():
        print(f"[seed] Warning: {samples_csv} not found, skipping frames.")
        return

    count = db.query(FrameDB).count()
    if count > 0:
        print(f"[seed] Frames already seeded ({count} rows). Skipping.")
        return

    records = []
    with open(samples_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            records.append(
                FrameDB(
                    sample_token=r["sample_token"],
                    sample_idx=int(r["sample_idx"]),
                    scene=r["scene"],
                    timestamp_s=float(r["timestamp_s"]),
                    split="mini_val",
                )
            )
    db.bulk_save_objects(records)
    db.commit()
    print(f"[seed] Successfully seeded {len(records)} frames.")


def seed_detections(db, lab_root: Path):
    count = db.query(DetectionDB).count()
    if count > 0:
        print(f"[seed] Detections already seeded ({count} rows). Skipping.")
        return

    total_inserted = 0
    for model_id, (rel_path, sensors, origin) in DETECTORS.items():
        csv_path = lab_root / rel_path
        if not csv_path.is_file():
            print(f"[seed] Skipping model {model_id}: file {rel_path} not found.")
            continue

        records = []
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                records.append(
                    DetectionDB(
                        sample_token=r.get("sample_token", ""),
                        sample_idx=int(r.get("sample_idx", 0)),
                        model_id=model_id,
                        class_name=r.get("class", ""),
                        x=float(r.get("x", 0.0)),
                        y=float(r.get("y", 0.0)),
                        z=float(r.get("z", 0.0)),
                        w=float(r.get("w", 0.0)),
                        l=float(r.get("l", 0.0)),
                        h=float(r.get("h", 0.0)),
                        yaw=float(r.get("yaw", 0.0)),
                        vx=float(r.get("vx", 0.0)),
                        vy=float(r.get("vy", 0.0)),
                        score=float(r.get("score", 0.0)),
                    )
                )
                if len(records) >= 2000:
                    db.bulk_save_objects(records)
                    db.commit()
                    total_inserted += len(records)
                    records = []

        if records:
            db.bulk_save_objects(records)
            db.commit()
            total_inserted += len(records)
        print(f"[seed] Model {model_id}: loaded records from {rel_path}")

    print(f"[seed] Total detections seeded: {total_inserted}")


def seed_benchmarks(db, lab_root: Path):
    try:
        from sqlalchemy import text
        db.execute(text("ALTER TABLE benchmarks ALTER COLUMN model_id TYPE VARCHAR(128);"))
        db.execute(text("ALTER TABLE benchmarks ALTER COLUMN sensor_setup TYPE VARCHAR(128);"))
        db.execute(text("ALTER TABLE benchmarks ALTER COLUMN origin TYPE VARCHAR(32);"))
        db.commit()
    except Exception:
        db.rollback()

    count = db.query(BenchmarkDB).count()
    if count > 0:
        print(f"[seed] Benchmarks already seeded ({count} rows). Skipping.")
        return

    comparison_csv = lab_root / "models/our_bevfusion_mini/comparison_table.csv"
    records = []
    if comparison_csv.is_file():
        with open(comparison_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                records.append(
                    BenchmarkDB(
                        model_id=r.get("model", r.get("method", "model")),
                        sensor_setup=r.get("modality", r.get("sensors", "all")),
                        origin="evaluation",
                        map_score=float(r["mAP"]) if "mAP" in r and r["mAP"] else None,
                        nds_score=float(r["NDS"]) if "NDS" in r and r["NDS"] else None,
                        latency_ms=float(r["latency_ms"]) if "latency_ms" in r and r["latency_ms"] else None,
                    )
                )
    if records:
        db.bulk_save_objects(records)
        db.commit()
        print(f"[seed] Seeded {len(records)} benchmark rows.")


def seed_benchmark_reports(db, lab_root: Path):
    sources = {
        "detection": "models/our_bevfusion_mini/metrics.json",
        "occupancy": "models/occupancy/metrics.json",
        "flow": "models/temporal_flow/metrics.json",
        "risk": "stage_h/results/risk_metrics.json",
    }
    for name, rel in sources.items():
        file_path = lab_root / rel
        if not file_path.is_file():
            print(f"[seed] Warning: {file_path} not found, skipping section {name}.")
            continue
        with open(file_path, encoding="utf-8-sig") as f:
            content = f.read()

        record = db.query(BenchmarkReportDB).filter(BenchmarkReportDB.section == name).first()
        if record:
            record.source = rel
            record.data_json = content
            print(f"[seed] Updated benchmark report section: {name}")
        else:
            db.add(BenchmarkReportDB(section=name, source=rel, data_json=content))
            print(f"[seed] Inserted benchmark report section: {name}")
    db.commit()


def main():
    print(f"[seed] Initializing database tables on: {engine.url.render_as_string(hide_password=True)}")
    Base.metadata.create_all(bind=engine)

    lab_root = get_settings().lab_data_root
    print(f"[seed] Reading source files from: {lab_root}")

    db = SessionLocal()
    try:
        seed_frames(db, lab_root)
        seed_detections(db, lab_root)
        seed_benchmarks(db, lab_root)
        seed_benchmark_reports(db, lab_root)
        print("[seed] Database seeding completed successfully!")
    finally:
        db.close()


if __name__ == "__main__":
    main()

