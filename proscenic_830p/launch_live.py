"""CLI: live-growing map snapshots, then coverage and dual-brush edge paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .live import LiveSnapshot, live_mapping_session
from .navigate import PlannedPose, plan_coverage, plan_edge_pass
from .occupancy import OccupancyGrid


def _fmt_pose(kind: str, pose: PlannedPose) -> str:
    i, j = pose.cell
    return (
        f"{kind} {pose.x_mm:.1f},{pose.y_mm:.1f},{pose.heading_deg:.1f} cell={i},{j}"
    )


def render_live(
    grid: OccupancyGrid,
    snapshots: tuple[LiveSnapshot, ...],
    coverage: tuple[PlannedPose, ...],
    edge: tuple[PlannedPose, ...],
) -> str:
    lines = [
        "# proscenic-830p live",
        f"resolution_mm={grid.resolution_mm}",
        f"snapshots={len(snapshots)}",
    ]
    for snap in snapshots:
        lines.append(
            f"SNAPSHOT {snap.index} known={snap.known} free={snap.free} "
            f"occupied={snap.occupied} unknown={snap.unknown}"
        )
    lines.append(f"COVERAGE_COUNT {len(coverage)}")
    for pose in coverage:
        lines.append(_fmt_pose("COVERAGE_POSE", pose))
    lines.append(f"EDGE_COUNT {len(edge)}")
    for pose in edge:
        lines.append(_fmt_pose("EDGE_POSE", pose))
    return "\n".join(lines) + "\n"


def run_live_file(path: str | Path) -> str:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    grid, snapshots = live_mapping_session(data)
    coverage = plan_coverage(grid)
    edge = plan_edge_pass(grid)
    return render_live(grid, snapshots, coverage, edge)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="proscenic-830p-live",
        description="Live Kartierung snapshots, then free-cell coverage and edge-brush pass.",
    )
    parser.add_argument("trace", help="JSON Kartierung fixture")
    parser.add_argument("-o", "--output", help="Also write canonical output to this path")
    args = parser.parse_args(argv)
    text = run_live_file(args.trace)
    sys.stdout.write(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
