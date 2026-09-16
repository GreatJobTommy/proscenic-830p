"""Live Kartierung: dock-origin occupancy + mapping-policy remote overlay."""

from __future__ import annotations

from .constants import MAPPING_BUMPER_STAMP_MM, MAPPING_RESOLUTION_MM
from .mapping import MappingPolicyState, next_mapping_move
from .occupancy import OccupancyGrid, PoseSample
from .probe import bumper_hit, integrate_pose
from .protocol import Fault, VacuumStatus, encode_direction

GRID_CELLS = 80
DOCK_MM = GRID_CELLS * MAPPING_RESOLUTION_MM / 2.0
DEFAULT_UNDOCK_TICKS = 16
LIVE_TURN_TICKS = 8


class KartierungSession:
    def __init__(
        self,
        undock_ticks: int = DEFAULT_UNDOCK_TICKS,
        live_drive: bool = True,
    ) -> None:
        self.undock_ticks = undock_ticks
        self.live_drive = live_drive
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
        self._ticks = 0
        self._prev_bumper = False
        self._turn_left = 0

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
        self._ticks = 0
        self._prev_bumper = False
        self._turn_left = 0

    def stop(self) -> None:
        self.running = False
        self.phase = "idle"
        self.reason = "stop"
        self.last_direction = "stop"

    def _policy_hit(self, raw_hit: bool) -> bool:
        if self._ticks <= self.undock_ticks:
            return False
        if not raw_hit:
            return False
        if self.last_direction == "forward":
            return True
        return raw_hit and not self._prev_bumper

    def tick(self, status: VacuumStatus | None, dt_s: float = 0.25) -> dict[str, str] | None:
        # DP 26 is a held overlay. Re-sending the same direction every tick
        # makes the 830P pulse forward/backward in place.
        if not self.running:
            return None
        self._ticks += 1
        moved = integrate_pose(self.pose, self.last_direction, dt_s)
        raw_hit = bumper_hit(status) if status is not None else False
        cliff = bool(status is not None and status.faults & Fault.OFF_GROUND)
        undocking = self._ticks <= self.undock_ticks
        hit = self._policy_hit(raw_hit)
        sample = PoseSample(
            x_mm=moved.x_mm,
            y_mm=moved.y_mm,
            heading_deg=moved.heading_deg,
            bumper=hit,
            cliff=False if undocking else cliff,
        )
        self.grid.observe(sample)
        self.pose = sample
        if self.live_drive:
            move_dir = self._live_direction(hit, undocking)
        elif undocking:
            move_dir = "forward"
            self.phase = "explore"
            self.reason = "undock"
            self.policy = MappingPolicyState()
        else:
            move, self.policy = next_mapping_move(
                sample, hit, self.grid, self.policy, dt_s=dt_s
            )
            move_dir = move.direction
            self.phase = self.policy.phase
            self.reason = move.reason
            if move.direction == "stop":
                self.running = False
        self._prev_bumper = raw_hit
        changed = move_dir != self.last_direction
        self.last_direction = move_dir
        if not changed:
            return None
        return encode_direction(move_dir)

    def _live_direction(self, hit: bool, undocking: bool) -> str:
        """Forward and left-turns only. Backward at the dock is the F/B rock."""
        if undocking:
            self.phase = "explore"
            self.reason = "undock"
            return "forward"
        if self._turn_left > 0:
            self._turn_left -= 1
            if self._turn_left == 0:
                self.phase = "explore"
                self.reason = "drive"
                return "forward"
            self.phase = "explore"
            self.reason = "turn"
            return "turnleft"
        if hit:
            self._turn_left = LIVE_TURN_TICKS
            self.phase = "explore"
            self.reason = "turn"
            return "turnleft"
        self.phase = "explore"
        self.reason = "drive"
        return "forward"
