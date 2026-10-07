"""Calibration audit figure: measured sensors + engine GT overlays, not predictions."""
import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.active_sensing.episode_inputs import RawEpisode  # noqa: E402

EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8)
         if bin(a ^ b).count("1") == 1]


def preview(root, output, index=0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    episode = RawEpisode(root)
    frame = episode.manifest["frames"][index]
    meta = json.loads((episode.root / frame["metadata"]["path"]).read_text())
    actors = json.loads((episode.root / meta["actor_ground_truth"]["path"]).read_text())["boxes"]
    fig = plt.figure(figsize=(15, 11), facecolor="#f6f8f9", layout="constrained")
    grid = fig.add_gridspec(4, 3, height_ratios=[.16, 1, 1, 1.25])
    header = fig.add_subplot(grid[0, :])
    header.axis("off")
    header.text(.02, .5, "P-027 / Active sensing — calibration evidence", va="center",
                size=18, weight="bold", color="#102c35")
    cameras = ["CAM_FRONT_LEFT", "CAM_FRONT", "CAM_FRONT_RIGHT",
               "CAM_BACK_LEFT", "CAM_BACK", "CAM_BACK_RIGHT"]
    for i, name in enumerate(cameras):
        ax = fig.add_subplot(grid[1 + i // 3, i % 3])
        sensor = meta["sensors"][name]
        image = Image.open(episode.root / sensor["artifact"]["path"])
        ax.imshow(image)
        inv = np.linalg.inv(sensor["optical_to_ego_lab"])
        intrinsic = np.asarray(sensor["intrinsic"])
        for box in actors:
            signs = np.array(list(itertools.product((-1, 1), repeat=3)))
            corners = signs * np.array(box["size_lwh"]) / 2
            corners = corners @ np.array(box["rotation_ego"]).T + box["center_ego"]
            optical = np.column_stack((corners, np.ones(8))) @ inv.T
            pixels = optical[:, :3] @ intrinsic.T
            uv = pixels[:, :2] / np.maximum(pixels[:, 2:3], 0.01)
            for a, b in EDGES:
                if min(optical[a, 2], optical[b, 2]) > 0.1:
                    ax.plot(uv[[a, b], 0], uv[[a, b], 1], color="#20ddbc", linewidth=1)
        ax.set_xlim(0, image.width)
        ax.set_ylim(image.height, 0)
        ax.set_title(name.removeprefix("CAM_").replace("_", " "), loc="left", fontsize=10, weight="bold")
        ax.axis("off")
    ax = fig.add_subplot(grid[3, :2], facecolor="#081d25")
    with np.load(episode.root / meta["sensors"]["LIDAR_TOP"]["artifact"]["path"]) as data:
        points = data["points_ego"]
        keep = (np.abs(points[:, :2]) < 55).all(axis=1)
        points = points[keep][::3]
        ax.scatter(-points[:, 1], points[:, 0], s=0.8, c=points[:, 2], cmap="viridis", vmin=-0.5, vmax=3, alpha=0.6)
    for name, sensor in meta["sensors"].items():
        if name.startswith("RADAR_"):
            with np.load(episode.root / sensor["artifact"]["path"]) as data:
                xyz = data["points_ego"]
                ax.scatter(-xyz[:, 1], xyz[:, 0], s=9, c="#ffb256", alpha=0.7)
    for box in actors:
        signs = np.array([[-1,-1,0], [-1,1,0], [1,1,0], [1,-1,0], [-1,-1,0]])
        corners = signs * np.array(box["size_lwh"]) / 2
        corners = corners @ np.array(box["rotation_ego"]).T + box["center_ego"]
        ax.plot(-corners[:, 1], corners[:, 0], color="#20ddbc", linewidth=1.4)
    ax.scatter([0], [0], s=70, c="white", marker="^")
    ax.set_xlim(-55, 55)
    ax.set_ylim(-55, 55)
    ax.set_aspect("equal")
    ax.set_title("LiDAR 32 + five radars · engine GT boxes", loc="left", fontsize=11, weight="bold")
    ax.set_xlabel("Right (m)")
    ax.set_ylabel("Forward (m)")
    ax.tick_params(colors="#536873", labelsize=8)
    info = fig.add_subplot(grid[3, 2])
    info.axis("off")
    info.text(0, .98, "SYNCHRONIZED SENSOR AUDIT", size=12, weight="bold", color="#102c35", va="top")
    info.text(0, .84, f"{episode.manifest['scenario']['map']} · {episode.manifest['scenario']['weather']}\n"
              f"CARLA frame {frame['frame_id']} · t={frame['timestamp']:.3f} s\n"
              f"{len(meta['sensors'])} streams · {len(actors)} engine actors\n"
              f"{frame['visible_actor_count']} actors observed by semantic LiDAR", size=10, linespacing=1.7, color="#3d5963", va="top")
    info.text(0, .47, "Green: engine ground truth\nOrange: CARLA radar returns\nCloud: input LiDAR height\n\nGT is a reference, not a prediction.\nNo model accuracy/GPU savings measured.",
              size=10, linespacing=1.7, color="#3d5963", va="top")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frame", type=int, default=0)
    args = parser.parse_args()
    preview(args.episode, args.output, args.frame)
