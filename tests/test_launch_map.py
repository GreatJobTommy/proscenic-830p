"""Launch entry must print the occupancy grid, including the sticky obstacle."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from proscenic_830p.launch_map import render_canonical, run_trace_file

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_launch_render_keeps_obstacle_after_squeeze(occupancy_trace_path: Path) -> None:
    grid = run_trace_file(occupancy_trace_path)
    text = render_canonical(grid)
    occupied_lines = [
        line for line in text.splitlines() if line.startswith("OCCUPIED_CELL ")
    ]
    assert occupied_lines, text
    # Bumper contact at (1065, 500) → cell (21, 10) with origin 0 and 50 mm cells.
    assert "OCCUPIED_CELL 21,10" in text
    assert "FREE_COUNT " in text
    assert "UNKNOWN_COUNT " in text
    report = grid.report()
    assert report.occupied >= 1
    assert grid.cell_at(1065, 500).name == "OCCUPIED"
    assert grid.cell_at(2000, 1500).name == "UNKNOWN"


def test_launch_module_from_fresh_consumer(occupancy_trace_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "proscenic_830p.launch_map", str(occupancy_trace_path)],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OCCUPIED_CELL 21,10" in proc.stdout
    assert "UNKNOWN_COUNT " in proc.stdout
