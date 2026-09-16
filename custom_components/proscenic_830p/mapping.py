"""Kartierung pass: dock-marked occupancy + multi-angle mapping drive.

The 830P has no LiDAR. This pass dead-reckons a pose + bumper stream, keeps
occupied cells sticky, and after the first hit on a compact obstacle
re-approaches from a second heading (circumnavigate) instead of only
bump-then-turn-left.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .constants import (
    BODY_RADIUS_MM,
    MAPPING_BUMPER_STAMP_MM,
    MAPPING_RESOLUTION_MM,
)
from .occupancy import OccupancyGrid, PoseSample, scan_probe
from .probe import DEFAULT_SPEED_MM_S, DEFAULT_TURN_DEG_S, integrate_pose

BACKOFF_MM = 220.0
FLANK_MM = 540.0
PASS_MM = 420.0
HEADING_TOL_DEG = 12.0


@dataclass(frozen=True)
class MappingMove:
    direction: str
    reason: str


@dataclass(frozen=True)
class MappingPolicyState:
    phase: str = "explore"
    hit_headings_deg: tuple[float, ...] = ()
    last_hit_heading_deg: float | None = None
    progress_mm: float = 0.0
    target_heading_deg: float | None = None


@dataclass(frozen=True)
class MappingRun:
    grid: OccupancyGrid
    samples: tuple[PoseSample, ...]
    hit_headings_deg: tuple[float, ...]
    hit_poses: tuple[PoseSample, ...]


def normalize_heading_deg(heading_deg: float) -> float:
    return heading_deg % 360.0


def angle_diff_deg(target_deg: float, current_deg: float) -> float:
    """Signed smallest turn from current to target; positive is left/CCW."""
    return (target_deg - current_deg + 180.0) % 360.0 - 180.0


def bumper_against_aabb(
    pose: PoseSample,
    aabb: tuple[float, float, float, float],
    radius_mm: float = BODY_RADIUS_MM,
) -> bool:
    xmin, xmax, ymin, ymax = aabb
    if xmin <= pose.x_mm <= xmax and ymin <= pose.y_mm <= ymax:
        return True
    rad = math.radians(pose.heading_deg)
    cx = pose.x_mm + radius_mm * math.cos(rad)
    cy = pose.y_mm + radius_mm * math.sin(rad)
    qx = min(max(cx, xmin), xmax)
    qy = min(max(cy, ymin), ymax)
    return math.hypot(cx - qx, cy - qy) <= 12.0


def _turn_toward(error_deg: float) -> str:
    if error_deg > 0:
        return "turnleft"
    return "turnright"


def next_mapping_move(
    pose: PoseSample,
    bumper: bool,
    grid: OccupancyGrid,
    state: MappingPolicyState,
    dt_s: float = 0.2,
    speed_mm_s: float = DEFAULT_SPEED_MM_S,
    turn_deg_s: float = DEFAULT_TURN_DEG_S,
) -> tuple[MappingMove, MappingPolicyState]:
    """Choose the next remote-control overlay command from pose, bumper, grid."""
    del grid  # occupancy is available for future frontier search; policy is geometric
    step_mm = speed_mm_s * dt_s
    heading = normalize_heading_deg(pose.heading_deg)

    if bumper and state.phase not in {"backoff", "turn_flank"}:
        headings = state.hit_headings_deg + (heading,)
        last = heading
        if len(headings) >= 2:
            return MappingMove("backward", "mapped-backoff"), replace(
                state,
                phase="mapped",
                hit_headings_deg=headings,
                last_hit_heading_deg=last,
                progress_mm=0.0,
            )
        flank = normalize_heading_deg(last + 90.0)
        return MappingMove("backward", "backoff"), replace(
            state,
            phase="backoff",
            hit_headings_deg=headings,
            last_hit_heading_deg=last,
            target_heading_deg=flank,
            progress_mm=0.0,
        )

    if state.phase == "mapped":
        return MappingMove("stop", "mapped"), state

    if state.phase == "backoff":
        progressed = state.progress_mm + step_mm
        if progressed >= BACKOFF_MM:
            return MappingMove("turnleft", "turn-flank"), replace(
                state, phase="turn_flank", progress_mm=0.0
            )
        return MappingMove("backward", "backoff"), replace(
            state, progress_mm=progressed
        )

    if state.phase == "turn_flank":
        target = state.target_heading_deg if state.target_heading_deg is not None else heading
        err = angle_diff_deg(target, heading)
        if abs(err) <= HEADING_TOL_DEG:
            return MappingMove("forward", "flank"), replace(
                state, phase="flank", progress_mm=0.0
            )
        return MappingMove(_turn_toward(err), "turn-flank"), state

    if state.phase == "flank":
        progressed = state.progress_mm + step_mm
        if progressed >= FLANK_MM:
            original = state.last_hit_heading_deg if state.last_hit_heading_deg is not None else 0.0
            return MappingMove("turnright", "turn-pass"), replace(
                state,
                phase="turn_pass",
                target_heading_deg=normalize_heading_deg(original),
                progress_mm=0.0,
            )
        return MappingMove("forward", "flank"), replace(state, progress_mm=progressed)

    if state.phase == "turn_pass":
        target = state.target_heading_deg if state.target_heading_deg is not None else heading
        err = angle_diff_deg(target, heading)
        if abs(err) <= HEADING_TOL_DEG:
            return MappingMove("forward", "pass"), replace(
                state, phase="pass", progress_mm=0.0
            )
        return MappingMove(_turn_toward(err), "turn-pass"), state

    if state.phase == "pass":
        progressed = state.progress_mm + step_mm
        if progressed >= PASS_MM:
            original = state.last_hit_heading_deg if state.last_hit_heading_deg is not None else 0.0
            reapproach = normalize_heading_deg(original - 90.0)
            return MappingMove("turnright", "turn-reapproach"), replace(
                state,
                phase="turn_reapproach",
                target_heading_deg=reapproach,
                progress_mm=0.0,
            )
        return MappingMove("forward", "pass"), replace(state, progress_mm=progressed)

    if state.phase == "turn_reapproach":
        target = state.target_heading_deg if state.target_heading_deg is not None else heading
        err = angle_diff_deg(target, heading)
        if abs(err) <= HEADING_TOL_DEG:
            return MappingMove("forward", "reapproach"), replace(
                state, phase="reapproach", progress_mm=0.0
            )
        return MappingMove(_turn_toward(err), "turn-reapproach"), state

    if state.phase == "reapproach":
        progressed = state.progress_mm + step_mm
        if progressed >= 900.0:
            return MappingMove("stop", "reapproach-timeout"), replace(
                state, phase="mapped", progress_mm=progressed
            )
        return MappingMove("forward", "reapproach"), replace(
            state, progress_mm=progressed
        )

    return MappingMove("forward", "explore"), state


def run_mapping_pass(data: Mapping[str, object]) -> OccupancyGrid:
    """Fill a Kartierung grid from a fixture: mark dock, then pose+bumper stream."""
    dock = data["dock"]  # type: ignore[index]
    grid = OccupancyGrid(
        resolution_mm=int(data.get("resolution_mm", MAPPING_RESOLUTION_MM)),
        origin_x_mm=float(data.get("origin_x_mm", 0)),
        origin_y_mm=float(data.get("origin_y_mm", 0)),
        width_cells=int(data.get("width_cells", 80)),
        height_cells=int(data.get("height_cells", 60)),
        bumper_stamp_radius_mm=float(
            data.get("bumper_stamp_radius_mm", MAPPING_BUMPER_STAMP_MM)
        ),
    )
    grid.mark_dock(
        float(dock["x_mm"]),  # type: ignore[index]
        float(dock["y_mm"]),  # type: ignore[index]
        float(dock.get("heading_deg", 0) or 0),  # type: ignore[union-attr]
    )
    raw_samples: Sequence[object] = data["samples"]  # type: ignore[assignment]
    samples = [
        s if isinstance(s, PoseSample) else PoseSample.from_mapping(s)  # type: ignore[arg-type]
        for s in raw_samples
    ]
    return scan_probe(samples, grid=grid)


def run_mapping_policy(
    dock: PoseSample,
    post_aabb: tuple[float, float, float, float],
    *,
    max_steps: int = 500,
    dt_s: float = 0.2,
    speed_mm_s: float = DEFAULT_SPEED_MM_S,
    turn_deg_s: float = 90.0,
    width_cells: int = 80,
    height_cells: int = 60,
) -> MappingRun:
    """Simulate the mapping drive around a rectangular post (no live robot)."""
    grid = OccupancyGrid(
        resolution_mm=MAPPING_RESOLUTION_MM,
        origin_x_mm=0.0,
        origin_y_mm=0.0,
        width_cells=width_cells,
        height_cells=height_cells,
        bumper_stamp_radius_mm=MAPPING_BUMPER_STAMP_MM,
    )
    grid.mark_dock(dock.x_mm, dock.y_mm, dock.heading_deg)
    pose = dock
    state = MappingPolicyState()
    samples: list[PoseSample] = []
    hit_headings: list[float] = []
    hit_poses: list[PoseSample] = []
    for _ in range(max_steps):
        hit = bumper_against_aabb(pose, post_aabb)
        sample = PoseSample(
            x_mm=pose.x_mm,
            y_mm=pose.y_mm,
            heading_deg=pose.heading_deg,
            bumper=hit,
        )
        grid.observe(sample)
        samples.append(sample)
        if hit:
            hit_headings.append(normalize_heading_deg(pose.heading_deg))
            hit_poses.append(sample)
            if len(hit_headings) >= 2:
                break
        move, state = next_mapping_move(
            sample,
            hit,
            grid,
            state,
            dt_s=dt_s,
            speed_mm_s=speed_mm_s,
            turn_deg_s=turn_deg_s,
        )
        if move.direction == "stop":
            break
        pose = integrate_pose(
            pose,
            move.direction,
            dt_s,
            speed_mm_s=speed_mm_s,
            turn_deg_s=turn_deg_s,
        )
    return MappingRun(
        grid=grid,
        samples=tuple(samples),
        hit_headings_deg=tuple(hit_headings),
        hit_poses=tuple(hit_poses),
    )
