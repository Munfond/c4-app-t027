"""SQLAlchemy ORM models for ADAS perception lab."""

from sqlalchemy import Column, Float, Integer, LargeBinary, String, Text

from src.database import Base


class FrameDB(Base):
    __tablename__ = "frames"

    sample_token = Column(String(64), primary_key=True, index=True)
    sample_idx = Column(Integer, index=True, nullable=False)
    scene = Column(String(32), index=True, nullable=False)
    timestamp_s = Column(Float, nullable=False)
    split = Column(String(16), default="mini_val", nullable=False)


class DetectionDB(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_token = Column(String(64), index=True, nullable=False)
    sample_idx = Column(Integer, index=True, nullable=False)
    model_id = Column(String(32), index=True, nullable=False)
    class_name = Column(String(32), index=True, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    z = Column(Float, nullable=False)
    w = Column(Float, nullable=False)
    l = Column(Float, nullable=False)  # noqa: E741
    h = Column(Float, nullable=False)
    yaw = Column(Float, nullable=False)
    vx = Column(Float, default=0.0, nullable=False)
    vy = Column(Float, default=0.0, nullable=False)
    score = Column(Float, index=True, nullable=False)


class BenchmarkDB(Base):
    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(128), index=True, nullable=False)
    sensor_setup = Column(String(128), nullable=False)
    origin = Column(String(32), nullable=False)
    map_score = Column(Float, nullable=True)
    nds_score = Column(Float, nullable=True)
    latency_ms = Column(Float, nullable=True)
    details_json = Column(Text, nullable=True)


class CameraImageDB(Base):
    __tablename__ = "camera_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_token = Column(String(64), index=True, nullable=False)
    channel = Column(String(32), index=True, nullable=False)
    image_data = Column(LargeBinary, nullable=False)


class EnvironmentDB(Base):
    __tablename__ = "environments"

    sample_token = Column(String(64), primary_key=True, index=True)
    payload_json = Column(Text, nullable=False)

