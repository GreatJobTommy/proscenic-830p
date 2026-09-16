"""Scan/probe overlay: bumper faults from 830P status drive occupancy + next move."""

from __future__ import annotations

from proscenic_830p.occupancy import Cell, OccupancyGrid, PoseSample
from proscenic_830p.probe import bumper_hit, direction_for_probe, integrate_pose, probe_tick
from proscenic_830p.protocol import decode_status, encode_direction


def test_bumper_hit_reads_collision_and_cliff_fault_bits(dps_payloads: dict) -> None:
    assert bumper_hit(decode_status(dps_payloads["status_fault_bumper"])) is True
    assert bumper_hit(decode_status(dps_payloads["status_fault_cliff"])) is True
    assert bumper_hit(decode_status(dps_payloads["status_smart_cleaning"])) is False


def test_probe_policy_turns_on_bumper() -> None:
    assert direction_for_probe(False) == "forward"
    assert direction_for_probe(True) == "turnleft"


def test_integrate_pose_forward_uses_heading() -> None:
    pose = integrate_pose(
        PoseSample(x_mm=0, y_mm=0, heading_deg=0),
        "forward",
        dt_s=1.0,
        speed_mm_s=200.0,
    )
    assert pose.x_mm == 200.0
    assert pose.y_mm == 0.0
    left = integrate_pose(
        PoseSample(x_mm=0, y_mm=0, heading_deg=90),
        "turnleft",
        dt_s=1.0,
        turn_deg_s=45.0,
    )
    assert left.heading_deg == 135.0


def test_probe_tick_marks_occupied_and_requests_turn(dps_payloads: dict) -> None:
    grid = OccupancyGrid(
        resolution_mm=50, origin_x_mm=0, origin_y_mm=0, width_cells=50, height_cells=40
    )
    pose = PoseSample(x_mm=900, y_mm=500, heading_deg=0)
    status = decode_status(dps_payloads["status_fault_bumper"])
    new_pose, command = probe_tick(grid, pose, status, dt_s=0.0)
    assert grid.cell_at(1065, 500) is Cell.OCCUPIED
    assert command == encode_direction("turnleft")
    assert new_pose.bumper is True
