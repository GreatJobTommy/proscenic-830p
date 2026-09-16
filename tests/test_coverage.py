"""Map-guided coverage stays on free cells of a finished Kartierung grid."""

from __future__ import annotations

import json
from pathlib import Path

from proscenic_830p.live import live_mapping_session
from proscenic_830p.navigate import body_clears_occupied, plan_coverage
from proscenic_830p.occupancy import Cell

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kartierung_post.json"


def test_coverage_path_stays_on_free_cells_only() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    grid, _ = live_mapping_session(data)
    path = plan_coverage(grid)
    assert len(path) > 1
    cells = [p.cell for p in path]
    assert len(set(cells)) > 1
    occupied = set(grid.report().occupied_cells)
    free = set(grid.report().free_cells)
    ux, uy = data["meta"]["unvisited_mm"]
    unknown_cell = grid.world_to_cell(ux, uy)
    for pose in path:
        assert grid.cell_at(pose.x_mm, pose.y_mm) is Cell.FREE
        assert pose.cell in free
        assert pose.cell not in occupied
        assert pose.cell != unknown_cell
        assert grid.cell_index(*pose.cell) is Cell.FREE
        # Body disk must not sit on occupied (rim contact only).
        assert body_clears_occupied(grid, pose.x_mm, pose.y_mm)
