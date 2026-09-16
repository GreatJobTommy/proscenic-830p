"""Edge/Kanten pass: free-cell path with side brushes on occupied frontier."""

from __future__ import annotations

import json
from pathlib import Path

from proscenic_830p.live import live_mapping_session
from proscenic_830p.navigate import (
    body_clears_occupied,
    brush_touches_occupied,
    plan_edge_pass,
    side_brush_points,
)
from proscenic_830p.occupancy import Cell
from proscenic_830p.protocol import Command, encode_command

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kartierung_post.json"


def test_edge_pass_is_map_path_not_tuya_wallfollow() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    grid, _ = live_mapping_session(data)
    path = plan_edge_pass(grid)
    assert path
    assert encode_command(Command.WALL_FOLLOW) == {"25": "wallfollow"}
    assert all(hasattr(p, "x_mm") and hasattr(p, "heading_deg") for p in path)
    assert not any(p == encode_command(Command.WALL_FOLLOW) for p in path)


def test_edge_pass_keeps_body_free_and_side_brush_on_occupied() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    grid, _ = live_mapping_session(data)
    path = plan_edge_pass(grid)
    assert len(path) >= 1
    touches = 0
    for pose in path:
        assert grid.cell_at(pose.x_mm, pose.y_mm) is Cell.FREE
        assert body_clears_occupied(grid, pose.x_mm, pose.y_mm)
        left, right = side_brush_points(pose.x_mm, pose.y_mm, pose.heading_deg)
        hit_left = brush_touches_occupied(grid, left)
        hit_right = brush_touches_occupied(grid, right)
        assert hit_left or hit_right
        if hit_left:
            touches += 1
        if hit_right:
            touches += 1
    assert touches >= 1
