"""Launch entry for the Kartierung fixture: dock + post, deterministic twice."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from proscenic_830p.launch_kartierung import render_kartierung, run_kartierung_file

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "kartierung_post.json"


def test_kartierung_render_has_dock_and_post() -> None:
    grid = run_kartierung_file(FIXTURE)
    text = render_kartierung(grid)
    assert "DOCK_POSE " in text
    assert "DOCK_CELL " in text
    assert "OCCUPIED_CELL " in text
    assert grid.dock_cells
    assert grid.cell_at(850, 500).name == "OCCUPIED"
    assert grid.cell_at(200, 500).name == "FREE"
    assert (grid.world_to_cell(200, 500)) in grid.dock_cells
    assert grid.cell_at(1800, 1400).name == "UNKNOWN"
    assert "resolution_mm=25" in text


def test_kartierung_module_from_fresh_consumer() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "proscenic_830p.launch_kartierung", str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "DOCK_CELL " in proc.stdout
    assert "OCCUPIED_CELL " in proc.stdout
    assert "resolution_mm=25" in proc.stdout
