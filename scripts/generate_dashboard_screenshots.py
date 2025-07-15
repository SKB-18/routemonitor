"""Generate static dashboard screenshots for docs/ (Phase 6 portfolio).

    python scripts/generate_dashboard_screenshots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

plt.style.use("dark_background")


def _save(name: str) -> None:
    path = DOCS / name
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor="#0e1117")
    plt.close()
    print(f"  wrote {path}")


def route_timeline() -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(20)
    updates = np.random.randint(2, 12, 20)
    withdraws = np.random.randint(0, 5, 20)
    ax.bar(x - 0.2, updates, 0.4, label="UPDATE", color="#2ecc71")
    ax.bar(x + 0.2, withdraws, 0.4, label="WITHDRAW", color="#e74c3c")
    ax.set_title("Route Timeline — BGP UPDATE / WITHDRAW Events", fontsize=14)
    ax.set_xlabel("Time bucket (2 min)")
    ax.set_ylabel("Event count")
    ax.legend()
    _save("route_timeline.png")


def device_health() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    speakers = ["core-r1", "core-r2", "edge-r1", "edge-r2"]
    axes[0].bar(speakers, [99.8, 99.2, 97.5, 99.9], color="#3498db")
    axes[0].set_title("Speaker Uptime %")
    axes[0].set_ylim(90, 100)
    colors = ["#2ecc71", "#f1c40f", "#e74c3c", "#2ecc71"]
    axes[1].bar(speakers, [2, 8, 45, 1], color=colors)
    axes[1].set_title("Flap Count (24h)")
    fig.suptitle("Device Health — BGP Speaker Status", fontsize=14)
    _save("device_health.png")


def anomaly_timeline() -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(12)
    y = [2, 3, 4, 5, 8, 15, 42, 38, 12, 6, 4, 3]
    ax.plot(x, y, marker="o", color="#e67e22", linewidth=2)
    ax.axhline(20, color="#f39c12", linestyle="--", label="threshold")
    ax.fill_between(x, y, alpha=0.2, color="#e67e22")
    ax.set_title("Anomaly Timeline — Flap Rate vs Baseline", fontsize=14)
    ax.set_xlabel("Time (30 min buckets)")
    ax.set_ylabel("Flap count")
    ax.legend()
    _save("anomaly_timeline.png")


def correlation_matrix() -> None:
    fig, ax = plt.subplots(figsize=(8, 7))
    labels = ["10.0.0.0/24", "10.1.0.0/24", "10.2.0.0/24", "192.168.0.0/24"]
    matrix = np.array(
        [
            [1.0, 0.82, 0.15, 0.71],
            [0.82, 1.0, 0.22, 0.65],
            [0.15, 0.22, 1.0, 0.18],
            [0.71, 0.65, 0.18, 1.0],
        ]
    )
    im = ax.imshow(matrix, cmap="RdYlGn_r", vmin=0, vmax=1)
    ax.set_xticks(range(4), labels, rotation=45, ha="right")
    ax.set_yticks(range(4), labels)
    ax.set_title("Prefix Correlation Matrix — Co-failure Heatmap", fontsize=13)
    plt.colorbar(im, ax=ax, fraction=0.046)
    _save("correlation_matrix.png")


def dashboard_hero() -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        "RouteMonitor — BGP Telemetry Dashboard", fontsize=16, fontweight="bold"
    )
    axes[0, 0].bar(["UPDATE", "WITHDRAW"], [128, 24], color=["#2ecc71", "#e74c3c"])
    axes[0, 0].set_title("Route Timeline")
    axes[0, 1].bar(["r1", "r2", "r3"], [99, 97, 99], color="#3498db")
    axes[0, 1].set_title("Device Health")
    axes[1, 0].plot([2, 3, 5, 8, 42, 30, 12, 6], marker="o", color="#e67e22")
    axes[1, 0].set_title("Anomaly Timeline")
    axes[1, 1].imshow([[1, 0.8], [0.8, 1]], cmap="RdYlGn_r")
    axes[1, 1].set_title("Correlation Matrix")
    _save("dashboard_screenshot.png")


def main() -> None:
    print("Generating dashboard screenshots → docs/")
    route_timeline()
    device_health()
    anomaly_timeline()
    correlation_matrix()
    dashboard_hero()
    print("Done.")


if __name__ == "__main__":
    main()
