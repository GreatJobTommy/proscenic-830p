"""Live occupancy: one sample at a time, known cells only grow."""

from __future__ import annotations

import json
from pathlib import Path

from proscenic_830p.live import live_mapping_session
from proscenic_830p.mapping import run_mapping_pass
from proscenic_830p.occupancy import Cell

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kartierung_post.json"


def test_live_snapshots_grow_and_match_oneshot() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    grid, snapshots = live_mapping_session(data)
    assert snapshots
    known_counts = [snap.known for snap in snapshots]
    assert known_counts == sorted(known_counts)
    assert known_counts[-1] >= known_counts[0]
    assert known_counts[-1] > 0

    oneshot = run_mapping_pass(data)
    live_report = grid.report()
    full = oneshot.report()
    assert live_report.free == full.free
    assert live_report.occupied == full.occupied
    assert live_report.unknown == full.unknown
    assert set(live_report.occupied_cells) == set(full.occupied_cells)
    assert set(live_report.free_cells) == set(full.free_cells)

    ux, uy = data["meta"]["unvisited_mm"]
    assert grid.cell_at(ux, uy) is Cell.UNKNOWN
    assert snapshots[-1].unknown == full.unknown
