"""Kartierung pass: dock marker, 100 mm post, multi-angle policy (shipped functions)."""

from __future__ import annotations

import json
from pathlib import Path

from proscenic_830p.constants import (
    BODY_RADIUS_MM,
    MAPPING_BUMPER_STAMP_MM,
    MAPPING_RESOLUTION_MM,
)
from proscenic_830p.mapping import (
    MappingPolicyState,
    bumper_against_aabb,
    next_mapping_move,
    run_mapping_pass,
    run_mapping_policy,
)
from proscenic_830p.occupancy import Cell, PoseSample

FIXTURES = Path(__file__).resolve().parent / "fixtures"
KARTIERUNG = FIXTURES / "kartierung_post.json"


def _load() -> dict:
    return json.loads(KARTIERUNG.read_text(encoding="utf-8"))


def test_mapping_resolution_resolves_100mm_post_on_both_axes() -> None:
    assert MAPPING_RESOLUTION_MM < 50
    assert 100 / MAPPING_RESOLUTION_MM > 1
    data = _load()
    assert data["resolution_mm"] == MAPPING_RESOLUTION_MM
    post = data["post"]
    cells_x = (post["xmax"] - post["xmin"]) / data["resolution_mm"]
    cells_y = (post["ymax"] - post["ymin"]) / data["resolution_mm"]
    assert cells_x > 1
    assert cells_y > 1


def test_mapping_pass_marks_dock_and_keeps_post_after_circumnavigate() -> None:
    data = _load()
    grid = run_mapping_pass(data)
    dock = data["dock"]
    post = data["post"]
    meta = data["meta"]

    assert grid.resolution_mm == MAPPING_RESOLUTION_MM
    assert grid.dock_pose is not None
    assert grid.dock_pose[0] == dock["x_mm"]
    assert grid.dock_pose[1] == dock["y_mm"]
    dock_cell = grid.world_to_cell(dock["x_mm"], dock["y_mm"])
    assert dock_cell in grid.dock_cells
    assert grid.cell_at(dock["x_mm"], dock["y_mm"]) is Cell.FREE

    first = meta["first_hit_pose_mm"]
    contact_x = first[0] + BODY_RADIUS_MM
    contact_y = first[1]
    assert grid.cell_at(contact_x, contact_y) is Cell.OCCUPIED

    occupied_before_around = set(grid.report().occupied_cells)
    # Corridor north of the post is free (body passed) and does not flood the room.
    cx, cy = meta["corridor_mm"]
    assert grid.cell_at(cx, cy) is Cell.FREE
    ux, uy = meta["unvisited_mm"]
    assert grid.cell_at(ux, uy) is Cell.UNKNOWN
    assert occupied_before_around <= set(grid.report().occupied_cells)
    assert grid.cell_at(contact_x, contact_y) is Cell.OCCUPIED

    occupied = grid.report().occupied_cells
    near_post = []
    for i, j in occupied:
        px, py = grid.cell_center(i, j)
        if (
            post["xmin"] - 80 <= px <= post["xmax"] + 80
            and post["ymin"] - 80 <= py <= post["ymax"] + 80
        ):
            near_post.append((i, j))
    assert near_post
    xs = [c[0] for c in near_post]
    ys = [c[1] for c in near_post]
    assert max(xs) - min(xs) >= 1
    assert max(ys) - min(ys) >= 1


def test_mapping_policy_backs_off_then_reapproaches_from_other_heading() -> None:
    data = _load()
    post = data["post"]
    aabb = (post["xmin"], post["xmax"], post["ymin"], post["ymax"])
    pose = PoseSample(x_mm=685, y_mm=500, heading_deg=0, bumper=True)
    from proscenic_830p.occupancy import OccupancyGrid

    grid = OccupancyGrid(
        resolution_mm=MAPPING_RESOLUTION_MM,
        width_cells=80,
        height_cells=60,
        bumper_stamp_radius_mm=MAPPING_BUMPER_STAMP_MM,
    )
    grid.observe(pose)
    move, state = next_mapping_move(pose, True, grid, MappingPolicyState())
    assert move.direction == "backward"
    assert move.direction != "turnleft"
    assert "backoff" in move.reason

    run = run_mapping_policy(
        PoseSample(x_mm=200, y_mm=500, heading_deg=0),
        aabb,
        max_steps=500,
        dt_s=0.2,
    )
    assert len(run.hit_headings_deg) >= 2
    first, second = run.hit_headings_deg[0], run.hit_headings_deg[1]
    delta = abs(((second - first + 180) % 360) - 180)
    assert delta > 45, (first, second, run.hit_headings_deg)
    # Second contact is still the post, from another heading.
    assert bumper_against_aabb(
        PoseSample(
            x_mm=run.hit_poses[1].x_mm,
            y_mm=run.hit_poses[1].y_mm,
            heading_deg=second,
            bumper=True,
        ),
        aabb,
    )
    assert run.grid.cell_at(850, 500) is Cell.OCCUPIED
    assert run.grid.cell_at(1800, 1400) is Cell.UNKNOWN
