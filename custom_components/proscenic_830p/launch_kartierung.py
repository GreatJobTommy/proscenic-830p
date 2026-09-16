"""CLI: Kartierung fixture → canonical grid with dock marker and occupied post."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .mapping import run_mapping_pass
from .occupancy import OccupancyGrid


def run_kartierung_file(path: str | Path) -> OccupancyGrid:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return run_mapping_pass(data)


def render_kartierung(grid: OccupancyGrid) -> str:
    report = grid.report()
    lines = [
        "# proscenic-830p kartierung",
        f"resolution_mm={grid.resolution_mm}",
        f"origin_mm={grid.origin_x_mm},{grid.origin_y_mm}",
        f"size_cells={grid.width_cells}x{grid.height_cells}",
    ]
    if grid.dock_pose is not None:
        x_mm, y_mm, heading = grid.dock_pose
        lines.append(f"DOCK_POSE {x_mm},{y_mm},{heading}")
    for i, j in sorted(grid.dock_cells):
        lines.append(f"DOCK_CELL {i},{j}")
    for i, j in sorted(report.occupied_cells):
        lines.append(f"OCCUPIED_CELL {i},{j}")
    lines.append(f"FREE_COUNT {report.free}")
    lines.append(f"OCCUPIED_COUNT {report.occupied}")
    lines.append(f"UNKNOWN_COUNT {report.unknown}")
    lines.append("ASCII")
    lines.extend(grid.ascii_lines())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="proscenic-830p-kartierung",
        description="Kartierung pass: dock + sticky occupancy from a pose+bumper fixture.",
    )
    parser.add_argument("trace", help="JSON fixture with dock, post, and samples[]")
    parser.add_argument("-o", "--output", help="Also write the canonical grid to this path")
    args = parser.parse_args(argv)
    grid = run_kartierung_file(args.trace)
    text = render_kartierung(grid)
    sys.stdout.write(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
