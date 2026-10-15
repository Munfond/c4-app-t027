"""Render the measured native profile pilot; plotted numbers come only from sealed audit."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="PNG output; paired SVG is also written")
    args = parser.parse_args()
    raw = args.report.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != args.report.with_suffix(".sha256").read_text().strip():
        raise ValueError("Audit report changed")
    data = json.loads(raw)
    if data["status"] != "complete_pilot" or len(data["profiles"]) != 12 or data["native_rl_admitted"] is not False:
        raise ValueError("Require complete research pilot")
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelcolor": "#192421",
            "xtick.color": "#607067",
            "ytick.color": "#607067",
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    fig.set_facecolor("#f2f2eb")
    fig.subplots_adjust(top=0.78, bottom=0.22, left=0.065, right=0.98, wspace=0.22)
    colors, markers = {16: "#617B86", 32: "#3B654F", 64: "#B47428"}, {16: "^", 32: "o", 64: "s"}
    for ax, key, title in zip(
        axes,
        ["occupied_iou", "object_recall"],
        ["Vùng chiếm dụng · Occupied IoU", "Vật thể · Object-cell recall"],
        strict=True,
    ):
        ax.set_facecolor("#ffffff")
        for channels in (16, 32, 64):
            rows = sorted(
                [r for r in data["profiles"] if r["channels"] == channels], key=lambda r: r["points_per_second"]
            )
            ax.plot(
                [r["sampled_lidar_bytes_per_second"] / 1e6 for r in rows],
                [r["metrics"][key] * 100 for r in rows],
                color=colors[channels],
                marker=markers[channels],
                markersize=7,
                linewidth=2,
                label=f"{channels} kênh",
            )
        ax.set_title(title, loc="left", fontweight="bold", fontsize=12, color="#10262e", pad=14)
        ax.set_ylim(25, 100)
        ax.set_xlim(1, 5.2)
        ax.set_xticks([1.2, 2.4, 3.6, 4.8])
        ax.set_ylabel("%")
        ax.set_xlabel("Payload lấy mẫu ước tính (MB/s)", labelpad=12)
        ax.grid(axis="y", color="#d6dbd2", linewidth=0.6)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, loc="lower right")
    fig.suptitle(
        "12 cấu hình LiDAR · giảm dữ liệu chưa giữ được chất lượng baseline",
        x=0.045,
        y=0.965,
        ha="left",
        fontsize=15,
        fontweight="bold",
        color="#10262e",
    )
    fig.text(
        0.045,
        0.05,
        "Town01 · 4 frame/profile · cùng reference · intensity adapter thử nghiệm · chưa admit RL native",
        fontsize=10,
        color="#607067",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        args.output, dpi=160, facecolor=fig.get_facecolor(), metadata={"Description": f"Sealed audit SHA256 {sha}"}
    )
    fig.savefig(
        args.output.with_suffix(".svg"),
        facecolor=fig.get_facecolor(),
        metadata={"Description": f"Sealed audit SHA256 {sha}"},
    )
    svg = args.output.with_suffix(".svg")
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)


if __name__ == "__main__":
    main()
