"""Drive the shipped occupancy + scan/probe functions (no re-implementation)."""

from __future__ import annotations

from proscenic_830p.constants import BODY_DIAMETER_MM, BODY_HEIGHT_MM, BODY_RADIUS_MM
from proscenic_830p.occupancy import (
    Cell,
    OccupancyGrid,
    PoseSample,
    apply_decoded_track,
    can_pass_under,
    scan_probe,
)


def _grid_from_trace(trace: dict) -> OccupancyGrid:
    samples = [PoseSample.from_mapping(s) for s in trace["samples"]]
    return scan_probe(
        samples,
        resolution_mm=trace["resolution_mm"],
        origin_x_mm=trace["origin_x_mm"],
        origin_y_mm=trace["origin_y_mm"],
        width_cells=trace["width_cells"],
        height_cells=trace["height_cells"],
    )


def test_body_constants_match_830p() -> None:
    assert BODY_DIAMETER_MM == 330
    assert BODY_RADIUS_MM == 165
    assert BODY_HEIGHT_MM == 76


def test_marks_free_along_330mm_wide_path(occupancy_trace: dict) -> None:
    grid = OccupancyGrid(
        resolution_mm=occupancy_trace["resolution_mm"],
        origin_x_mm=occupancy_trace["origin_x_mm"],
        origin_y_mm=occupancy_trace["origin_y_mm"],
        width_cells=occupancy_trace["width_cells"],
        height_cells=occupancy_trace["height_cells"],
    )
    # Mid-path pose before the bumper, so this assertion is only about body inflation.
    scan_probe(
        [PoseSample(x_mm=500, y_mm=500, heading_deg=0, bumper=False)],
        grid=grid,
    )
    assert grid.cell_at(500, 500) is Cell.FREE
    # Inside the 330 mm body disk (offset 100 mm < 165 mm radius).
    assert grid.cell_at(500, 600) is Cell.FREE
    # Outside the body disk (offset 250 mm > 165 mm) stays unknown — not flood-filled.
    assert grid.cell_at(500, 750) is Cell.UNKNOWN


def test_marks_occupied_on_bumper_hit(occupancy_trace: dict) -> None:
    grid = OccupancyGrid(
        resolution_mm=occupancy_trace["resolution_mm"],
        origin_x_mm=occupancy_trace["origin_x_mm"],
        origin_y_mm=occupancy_trace["origin_y_mm"],
        width_cells=occupancy_trace["width_cells"],
        height_cells=occupancy_trace["height_cells"],
    )
    scan_probe(
        [PoseSample(x_mm=900, y_mm=500, heading_deg=0, bumper=True)],
        grid=grid,
    )
    ox, oy = occupancy_trace["meta"]["obstacle_world_mm"]
    assert grid.cell_at(ox, oy) is Cell.OCCUPIED
    assert grid.cell_at(900, 500) is Cell.FREE


def test_squeeze_under_keeps_occupied_and_does_not_fill_unknown(
    occupancy_trace: dict,
) -> None:
    grid = _grid_from_trace(occupancy_trace)
    ox, oy = occupancy_trace["meta"]["obstacle_world_mm"]
    ux, uy = occupancy_trace["meta"]["unvisited_world_mm"]
    sx, sy = occupancy_trace["meta"]["squeeze_under_pose_mm"]
    px, py = occupancy_trace["meta"]["squeeze_past_pose_mm"]

    assert grid.cell_at(ox, oy) is Cell.OCCUPIED
    # Body later occupies the same XY (under-furniture / squeeze-through).
    assert grid.cell_at(sx, sy) is Cell.OCCUPIED
    # Parallel corridor is free, but the gap between the two paths is not filled in.
    assert grid.cell_at(px, py) is Cell.FREE
    assert grid.cell_at(1065, 700) is Cell.UNKNOWN
    assert grid.cell_at(ux, uy) is Cell.UNKNOWN
    report = grid.report()
    assert report.occupied >= 1
    assert report.free >= 1
    assert report.unknown > report.free
    assert (grid.world_to_cell(ox, oy)) in report.occupied_cells


def test_scan_probe_report_free_occupied_unknown(occupancy_trace: dict) -> None:
    grid = _grid_from_trace(occupancy_trace)
    report = grid.report()
    labels = {Cell.FREE, Cell.OCCUPIED, Cell.UNKNOWN}
    assert labels <= set(report.by_label)
    assert report.by_label[Cell.OCCUPIED] == report.occupied
    assert report.by_label[Cell.FREE] == report.free
    assert report.by_label[Cell.UNKNOWN] == report.unknown
    assert report.occupied + report.free + report.unknown == report.total


def test_occupied_never_demotes_when_body_overlaps() -> None:
    grid = OccupancyGrid(resolution_mm=50, width_cells=20, height_cells=20)
    scan_probe([PoseSample(x_mm=250, y_mm=250, heading_deg=0, bumper=True)], grid=grid)
    occupied_before = set(grid.report().occupied_cells)
    assert occupied_before
    # Drive the body through the bumper contact.
    scan_probe([PoseSample(x_mm=415, y_mm=250, heading_deg=0, bumper=False)], grid=grid)
    assert occupied_before <= set(grid.report().occupied_cells)
    for cell in occupied_before:
        assert grid.cell_index(*cell) is Cell.OCCUPIED


def test_decoded_track_marks_free_but_does_not_clear_occupied() -> None:
    grid = OccupancyGrid(resolution_mm=50, width_cells=20, height_cells=20)
    scan_probe([PoseSample(x_mm=200, y_mm=200, heading_deg=90, bumper=True)], grid=grid)
    occupied = set(grid.report().occupied_cells)
    apply_decoded_track(grid, [(200, 200), (250, 200), (300, 200)])
    assert occupied <= set(grid.report().occupied_cells)
    assert grid.cell_at(200, 200) is Cell.FREE or grid.cell_at(200, 200) is Cell.OCCUPIED
    assert grid.cell_at(300, 200) is Cell.FREE


def test_under_furniture_clearance_uses_76mm_body_height() -> None:
    assert can_pass_under(75) is False
    assert can_pass_under(76) is False
    assert can_pass_under(77) is True
