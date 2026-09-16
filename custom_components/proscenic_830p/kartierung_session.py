"""Live Kartierung: dock-origin occupancy + mapping-policy remote overlay."""

from __future__ import annotations

from .constants import MAPPING_BUMPER_STAMP_MM, MAPPING_RESOLUTION_MM
from .mapping import MappingPolicyState, next_mapping_move
from .occupancy import OccupancyGrid, PoseSample
from .probe import bumper_hit, integrate_pose
from .protocol import Fault, VacuumStatus, encode_direction

GRID_CELLS = 80
DOCK_MM = GRID_CELLS * MAPPING_RESOLUTION_MM / 2.0


class KartierungSession:
    def __init__(self) -> None:
        self.grid = OccupancyGrid(
            resolution_mm=MAPPING_RESOLUTION_MM,
            origin_x_mm=0.0,
            origin_y_mm=0.0,
            width_cells=GRID_CELLS,
            height_cells=GRID_CELLS,
            bumper_stamp_radius_mm=MAPPING_BUMPER_STAMP_MM,
        )
        self.pose = PoseSample(x_mm=DOCK_MM, y_mm=DOCK_MM, heading_deg=0.0)
        self.policy = MappingPolicyState()
        self.last_direction = "stop"
        self.running = False
        self.phase = "idle"
        self.reason = "idle"

    def start(self) -> None:
        self.grid = OccupancyGrid(
            resolution_mm=MAPPING_RESOLUTION_MM,
            origin_x_mm=0.0,
            origin_y_mm=0.0,
            width_cells=GRID_CELLS,
            height_cells=GRID_CELLS,
            bumper_stamp_radius_mm=MAPPING_BUMPER_STAMP_MM,
        )
        self.pose = PoseSample(x_mm=DOCK_MM, y_mm=DOCK_MM, heading_deg=0.0)
        self.grid.mark_dock(self.pose.x_mm, self.pose.y_mm, self.pose.heading_deg)
        self.grid.observe(self.pose)
        self.policy = MappingPolicyState()
        self.last_direction = "stop"
        self.running = True
        self.phase = "explore"
        self.reason = "start"

    def stop(self) -> None:
        self.running = False
        self.phase = "idle"
        self.reason = "stop"
        self.last_direction = "stop"

    def tick(self, status: VacuumStatus | None, dt_s: float = 0.25) -> dict[str, str]:
        if not self.running:
            return encode_direction("stop")
        moved = integrate_pose(self.pose, self.last_direction, dt_s)
        hit = bumper_hit(status) if status is not None else False
        cliff = bool(status is not None and status.faults & Fault.OFF_GROUND)
        sample = PoseSample(
            x_mm=moved.x_mm,
            y_mm=moved.y_mm,
            heading_deg=moved.heading_deg,
            bumper=hit,
            cliff=cliff,
        )
        self.grid.observe(sample)
        self.pose = sample
        move, self.policy = next_mapping_move(
            sample, hit, self.grid, self.policy, dt_s=dt_s
        )
        self.last_direction = move.direction
        self.phase = self.policy.phase
        self.reason = move.reason
        if move.direction == "stop":
            self.running = False
        return encode_direction(move.direction)
