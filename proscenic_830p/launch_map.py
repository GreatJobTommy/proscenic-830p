"""CLI launch entry: occupancy fixture → canonical grid (including sticky obstacles)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .occupancy import OccupancyGrid, PoseSample, scan_probe


def run_trace_file(path: str | Path) -> OccupancyGrid:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = [PoseSample.from_mapping(s) for s in data["samples"]]
    return scan_probe(
        samples,
        resolution_mm=int(data.get("resolution_mm", 50)),
        origin_x_mm=float(data.get("origin_x_mm", 0)),
        origin_y_mm=float(data.get("origin_y_mm", 0)),
        width_cells=int(data.get("width_cells", 80)),
        height_cells=int(data.get("height_cells", 40)),
    )


def render_canonical(grid: OccupancyGrid) -> str:
    report = grid.report()
    lines = [
        "# proscenic-830p occupancy",
        f"resolution_mm={grid.resolution_mm}",
        f"origin_mm={grid.origin_x_mm},{grid.origin_y_mm}",
        f"size_cells={grid.width_cells}x{grid.height_cells}",
    ]
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
        prog="proscenic-830p-map",
        description="Build a sticky occupancy grid from a pose+bumper trace.",
    )
    parser.add_argument("trace", help="JSON fixture with samples[] and grid size")
    parser.add_argument(
        "-o",
        "--output",
        help="Write the canonical grid to this path as well as stdout",
    )
    args = parser.parse_args(argv)
    grid = run_trace_file(args.trace)
    text = render_canonical(grid)
    sys.stdout.write(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
