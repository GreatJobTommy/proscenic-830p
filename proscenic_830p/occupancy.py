"""Sticky occupancy grid for the 330 mm / 76 mm 830P body.

Merge rule:
- UNKNOWN is the default.
- FREE is written only under the body disk that actually passed.
- OCCUPIED is written on bumper/cliff contact and never demotes to FREE.
- Traversing under furniture or squeezing past does not flood-fill unknown cells.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .constants import (
    BODY_HEIGHT_MM,
    BODY_RADIUS_MM,
    BUMPER_STAMP_RADIUS_MM,
    DEFAULT_RESOLUTION_MM,
)


class Cell(Enum):
    UNKNOWN = "unknown"
    FREE = "free"
    OCCUPIED = "occupied"


@dataclass(frozen=True)
class PoseSample:
    x_mm: float
    y_mm: float
    heading_deg: float = 0.0
    bumper: bool = False
    bumper_left: bool = False
    bumper_right: bool = False
    cliff: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "PoseSample":
        return cls(
            x_mm=float(data["x_mm"]),
            y_mm=float(data["y_mm"]),
            heading_deg=float(data.get("heading_deg", 0) or 0),
            bumper=bool(data.get("bumper", False)),
            bumper_left=bool(data.get("bumper_left", False)),
            bumper_right=bool(data.get("bumper_right", False)),
            cliff=bool(data.get("cliff", False)),
        )


@dataclass(frozen=True)
class ScanReport:
    free: int
    occupied: int
    unknown: int
    total: int
    occupied_cells: tuple[tuple[int, int], ...]
    free_cells: tuple[tuple[int, int], ...]
    by_label: dict[Cell, int]


class OccupancyGrid:
    def __init__(
        self,
        resolution_mm: int = DEFAULT_RESOLUTION_MM,
        origin_x_mm: float = 0.0,
        origin_y_mm: float = 0.0,
        width_cells: int = 80,
        height_cells: int = 40,
    ) -> None:
        self.resolution_mm = int(resolution_mm)
        self.origin_x_mm = float(origin_x_mm)
        self.origin_y_mm = float(origin_y_mm)
        self.width_cells = int(width_cells)
        self.height_cells = int(height_cells)
        self._cells: list[list[Cell]] = [
            [Cell.UNKNOWN for _ in range(self.width_cells)]
            for _ in range(self.height_cells)
        ]

    def in_bounds(self, i: int, j: int) -> bool:
        return 0 <= i < self.width_cells and 0 <= j < self.height_cells

    def world_to_cell(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        i = math.floor((x_mm - self.origin_x_mm) / self.resolution_mm)
        j = math.floor((y_mm - self.origin_y_mm) / self.resolution_mm)
        return i, j

    def cell_center(self, i: int, j: int) -> tuple[float, float]:
        return (
            self.origin_x_mm + (i + 0.5) * self.resolution_mm,
            self.origin_y_mm + (j + 0.5) * self.resolution_mm,
        )

    def cell_index(self, i: int, j: int) -> Cell:
        if not self.in_bounds(i, j):
            return Cell.UNKNOWN
        return self._cells[j][i]

    def cell_at(self, x_mm: float, y_mm: float) -> Cell:
        i, j = self.world_to_cell(x_mm, y_mm)
        return self.cell_index(i, j)

    def mark_free_body(self, x_mm: float, y_mm: float, heading_deg: float = 0.0) -> None:
        del heading_deg  # body is circular
        self._stamp(x_mm, y_mm, BODY_RADIUS_MM, Cell.FREE)

    def mark_occupied_bumper(
        self, x_mm: float, y_mm: float, heading_deg: float
    ) -> None:
        rad = math.radians(heading_deg)
        contact_x = x_mm + BODY_RADIUS_MM * math.cos(rad)
        contact_y = y_mm + BODY_RADIUS_MM * math.sin(rad)
        self._stamp(contact_x, contact_y, BUMPER_STAMP_RADIUS_MM, Cell.OCCUPIED)

    def observe(self, sample: PoseSample) -> None:
        self.mark_free_body(sample.x_mm, sample.y_mm, sample.heading_deg)
        if sample.bumper:
            self.mark_occupied_bumper(sample.x_mm, sample.y_mm, sample.heading_deg)
        if sample.bumper_left:
            self.mark_occupied_bumper(
                sample.x_mm, sample.y_mm, sample.heading_deg + 50.0
            )
        if sample.bumper_right:
            self.mark_occupied_bumper(
                sample.x_mm, sample.y_mm, sample.heading_deg - 50.0
            )
        if sample.cliff:
            self.mark_occupied_bumper(sample.x_mm, sample.y_mm, sample.heading_deg)

    def report(self) -> ScanReport:
        free_cells: list[tuple[int, int]] = []
        occupied_cells: list[tuple[int, int]] = []
        unknown = 0
        for j in range(self.height_cells):
            for i in range(self.width_cells):
                value = self._cells[j][i]
                if value is Cell.FREE:
                    free_cells.append((i, j))
                elif value is Cell.OCCUPIED:
                    occupied_cells.append((i, j))
                else:
                    unknown += 1
        occupied_cells_t = tuple(occupied_cells)
        free_cells_t = tuple(free_cells)
        total = self.width_cells * self.height_cells
        return ScanReport(
            free=len(free_cells_t),
            occupied=len(occupied_cells_t),
            unknown=unknown,
            total=total,
            occupied_cells=occupied_cells_t,
            free_cells=free_cells_t,
            by_label={
                Cell.FREE: len(free_cells_t),
                Cell.OCCUPIED: len(occupied_cells_t),
                Cell.UNKNOWN: unknown,
            },
        )

    def ascii_lines(self) -> list[str]:
        glyphs = {Cell.UNKNOWN: "?", Cell.FREE: ".", Cell.OCCUPIED: "#"}
        lines = []
        for j in range(self.height_cells - 1, -1, -1):
            row = "".join(glyphs[self._cells[j][i]] for i in range(self.width_cells))
            lines.append(row)
        return lines

    def _stamp(self, x_mm: float, y_mm: float, radius_mm: float, value: Cell) -> None:
        radius_sq = radius_mm * radius_mm
        i_min = math.floor((x_mm - radius_mm - self.origin_x_mm) / self.resolution_mm)
        i_max = math.floor((x_mm + radius_mm - self.origin_x_mm) / self.resolution_mm)
        j_min = math.floor((y_mm - radius_mm - self.origin_y_mm) / self.resolution_mm)
        j_max = math.floor((y_mm + radius_mm - self.origin_y_mm) / self.resolution_mm)
        for j in range(j_min, j_max + 1):
            for i in range(i_min, i_max + 1):
                if not self.in_bounds(i, j):
                    continue
                cx, cy = self.cell_center(i, j)
                if (cx - x_mm) ** 2 + (cy - y_mm) ** 2 > radius_sq:
                    continue
                current = self._cells[j][i]
                if value is Cell.OCCUPIED:
                    self._cells[j][i] = Cell.OCCUPIED
                elif value is Cell.FREE and current is not Cell.OCCUPIED:
                    self._cells[j][i] = Cell.FREE


def scan_probe(
    samples: Sequence[PoseSample | Mapping[str, object]],
    grid: OccupancyGrid | None = None,
    **grid_kwargs: object,
) -> OccupancyGrid:
    """Fill a grid from a pose + bumper stream in one pass (scan/probe mode)."""
    if grid is None:
        grid = OccupancyGrid(**grid_kwargs)  # type: ignore[arg-type]
    for raw in samples:
        sample = raw if isinstance(raw, PoseSample) else PoseSample.from_mapping(raw)
        grid.observe(sample)
    return grid


def apply_decoded_track(
    grid: OccupancyGrid, points: Iterable[tuple[float, float]]
) -> OccupancyGrid:
    """Overlay a decoded path/track. Occupied cells stay occupied."""
    for x_mm, y_mm in points:
        grid.mark_free_body(x_mm, y_mm)
    return grid


def can_pass_under(clearance_mm: float) -> bool:
    """The 76 mm body fits only when clearance is strictly greater than 76 mm."""
    return clearance_mm > BODY_HEIGHT_MM
