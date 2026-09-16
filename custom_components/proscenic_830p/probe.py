"""Scan/probe overlay: turn a pose + 830P status into occupancy and the next move.

The 830P does not expose a reliable local pose DP on Tuya 6668. Probe mode
therefore dead-reckons from DP 26 (direction) and treats fault bit 64
(collision/bumper) and 32 (cliff) as contacts. Gyro drift still applies.
"""

from __future__ import annotations

import math

from .occupancy import OccupancyGrid, PoseSample
from .protocol import Fault, VacuumStatus, encode_direction

DEFAULT_SPEED_MM_S = 200.0
DEFAULT_TURN_DEG_S = 60.0


def bumper_hit(status: VacuumStatus) -> bool:
    return bool(status.faults & (Fault.COLLISION_SENSOR | Fault.OFF_GROUND))


def direction_for_probe(hit: bool) -> str:
    return "turnleft" if hit else "forward"


def integrate_pose(
    pose: PoseSample,
    direction: str,
    dt_s: float,
    speed_mm_s: float = DEFAULT_SPEED_MM_S,
    turn_deg_s: float = DEFAULT_TURN_DEG_S,
) -> PoseSample:
    heading = pose.heading_deg
    x_mm = pose.x_mm
    y_mm = pose.y_mm
    if direction == "forward":
        rad = math.radians(heading)
        x_mm += speed_mm_s * dt_s * math.cos(rad)
        y_mm += speed_mm_s * dt_s * math.sin(rad)
    elif direction == "backward":
        rad = math.radians(heading)
        x_mm -= speed_mm_s * dt_s * math.cos(rad)
        y_mm -= speed_mm_s * dt_s * math.sin(rad)
    elif direction == "turnleft":
        heading += turn_deg_s * dt_s
    elif direction == "turnright":
        heading -= turn_deg_s * dt_s
    return PoseSample(x_mm=x_mm, y_mm=y_mm, heading_deg=heading, bumper=pose.bumper)


def probe_tick(
    grid: OccupancyGrid,
    pose: PoseSample,
    status: VacuumStatus,
    dt_s: float,
    last_direction: str = "forward",
    speed_mm_s: float = DEFAULT_SPEED_MM_S,
    turn_deg_s: float = DEFAULT_TURN_DEG_S,
) -> tuple[PoseSample, dict[str, str]]:
    """Advance occupancy from the last move and return the next DP 26 command."""
    moved = integrate_pose(
        pose,
        last_direction,
        dt_s,
        speed_mm_s=speed_mm_s,
        turn_deg_s=turn_deg_s,
    )
    hit = bumper_hit(status)
    sample = PoseSample(
        x_mm=moved.x_mm,
        y_mm=moved.y_mm,
        heading_deg=moved.heading_deg,
        bumper=hit,
        cliff=bool(status.faults & Fault.OFF_GROUND),
    )
    grid.observe(sample)
    return sample, encode_direction(direction_for_probe(hit))
