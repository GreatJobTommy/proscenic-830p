"""Map-guided coverage and dual side-brush edge (Kanten) pass."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .constants import BODY_RADIUS_MM, SIDE_BRUSH_OFFSET_DEG, SIDE_BRUSH_RADIUS_MM
from .occupancy import Cell, OccupancyGrid

_NEIGHBORS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_NEIGHBORS8 = tuple((di, dj) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj)


@dataclass(frozen=True)
class PlannedPose:
    x_mm: float
    y_mm: float
    heading_deg: float
    cell: tuple[int, int]


def side_brush_points(
    x_mm: float, y_mm: float, heading_deg: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Front-left and front-right brush tips on the 330 mm body disk."""
    rad = math.radians(heading_deg)
    left_a = rad + math.radians(SIDE_BRUSH_OFFSET_DEG)
    right_a = rad - math.radians(SIDE_BRUSH_OFFSET_DEG)
    left = (
        x_mm + SIDE_BRUSH_RADIUS_MM * math.cos(left_a),
        y_mm + SIDE_BRUSH_RADIUS_MM * math.sin(left_a),
    )
    right = (
        x_mm + SIDE_BRUSH_RADIUS_MM * math.cos(right_a),
        y_mm + SIDE_BRUSH_RADIUS_MM * math.sin(right_a),
    )
    return left, right


def occupied_centers(grid: OccupancyGrid) -> tuple[tuple[float, float], ...]:
    return tuple(grid.cell_center(i, j) for i, j in grid.report().occupied_cells)


def min_occupied_distance_mm(
    x_mm: float,
    y_mm: float,
    occupied_xy: tuple[tuple[float, float], ...],
) -> float:
    if not occupied_xy:
        return float("inf")
    return min(math.hypot(x_mm - ox, y_mm - oy) for ox, oy in occupied_xy)


def body_clearance_mm(grid: OccupancyGrid) -> float:
    """Occupied cell centres must stay outside the body interior (rim OK)."""
    return BODY_RADIUS_MM - float(grid.resolution_mm)


def body_clears_occupied(grid: OccupancyGrid, x_mm: float, y_mm: float) -> bool:
    """True if no occupied cell centre is deep inside the 330 mm body disk."""
    occ = occupied_centers(grid)
    return min_occupied_distance_mm(x_mm, y_mm, occ) >= body_clearance_mm(grid)


def cspace_free_cells(grid: OccupancyGrid) -> set[tuple[int, int]]:
    """FREE cells that are valid body-centre poses (disk not on occupied)."""
    occ = occupied_centers(grid)
    clearance = body_clearance_mm(grid)
    cells: set[tuple[int, int]] = set()
    for i, j in grid.report().free_cells:
        x_mm, y_mm = grid.cell_center(i, j)
        if min_occupied_distance_mm(x_mm, y_mm, occ) >= clearance:
            cells.add((i, j))
    return cells


def brush_touches_occupied(grid: OccupancyGrid, point: tuple[float, float]) -> bool:
    """True if the brush point is on or 8-adjacent to an occupied cell."""
    i, j = grid.world_to_cell(point[0], point[1])
    if grid.cell_index(i, j) is Cell.OCCUPIED:
        return True
    for di, dj in _NEIGHBORS8:
        if grid.cell_index(i + di, j + dj) is Cell.OCCUPIED:
            return True
    return False


def _bfs_free(
    start: tuple[int, int],
    goal: tuple[int, int],
    free: set[tuple[int, int]],
) -> list[tuple[int, int]] | None:
    if start == goal:
        return [start]
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            break
        i, j = cur
        for di, dj in _NEIGHBORS4:
            nxt = (i + di, j + dj)
            if nxt in free and nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    if goal not in prev:
        return None
    path: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path


def _heading_along(
    grid: OccupancyGrid, a: tuple[int, int], b: tuple[int, int]
) -> float:
    x1, y1 = grid.cell_center(*a)
    x2, y2 = grid.cell_center(*b)
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def _poses_from_cells(
    grid: OccupancyGrid, cells: list[tuple[int, int]]
) -> tuple[PlannedPose, ...]:
    poses: list[PlannedPose] = []
    for n, cell in enumerate(cells):
        x_mm, y_mm = grid.cell_center(*cell)
        heading = 0.0
        if n + 1 < len(cells):
            heading = _heading_along(grid, cell, cells[n + 1])
        elif n > 0:
            heading = _heading_along(grid, cells[n - 1], cell)
        poses.append(
            PlannedPose(x_mm=x_mm, y_mm=y_mm, heading_deg=heading, cell=cell)
        )
    return tuple(poses)


def plan_coverage(grid: OccupancyGrid) -> tuple[PlannedPose, ...]:
    """Boustrophedon coverage of reachable C-space cells (body disk off occupied)."""
    walkable = cspace_free_cells(grid)
    if not walkable:
        return ()
    start: tuple[int, int] | None = None
    if grid.dock_pose is not None:
        dock_cell = grid.world_to_cell(grid.dock_pose[0], grid.dock_pose[1])
        if dock_cell in walkable:
            start = dock_cell
    if start is None:
        start = min(walkable)

    by_row: dict[int, list[int]] = {}
    for i, j in walkable:
        by_row.setdefault(j, []).append(i)
    ordered: list[tuple[int, int]] = []
    for idx, j in enumerate(sorted(by_row)):
        cols = sorted(by_row[j])
        if idx % 2:
            cols.reverse()
        ordered.extend((i, j) for i in cols)
    if start in ordered:
        k = ordered.index(start)
        ordered = ordered[k:] + ordered[:k]

    path: list[tuple[int, int]] = [start]
    visited = {start}
    for target in ordered:
        if target in visited:
            continue
        segment = _bfs_free(path[-1], target, walkable)
        if not segment:
            continue
        for cell in segment[1:]:
            path.append(cell)
            visited.add(cell)
    return _poses_from_cells(grid, path)


def _heading_brush_toward_occupied(
    grid: OccupancyGrid,
    x_mm: float,
    y_mm: float,
    occupied_xy: tuple[tuple[float, float], ...],
) -> float | None:
    if not occupied_xy:
        return None
    ox, oy = min(occupied_xy, key=lambda p: math.hypot(x_mm - p[0], y_mm - p[1]))
    bearing = math.degrees(math.atan2(oy - y_mm, ox - x_mm))
    for heading in (
        bearing - SIDE_BRUSH_OFFSET_DEG,
        bearing + SIDE_BRUSH_OFFSET_DEG,
    ):
        heading = heading % 360.0
        left, right = side_brush_points(x_mm, y_mm, heading)
        if brush_touches_occupied(grid, left) or brush_touches_occupied(grid, right):
            return heading
    return None


def plan_edge_pass(grid: OccupancyGrid) -> tuple[PlannedPose, ...]:
    """C-space poses ~body-radius from occupied, side brush on the Rand."""
    occ_xy = occupied_centers(grid)
    walkable = cspace_free_cells(grid)
    if not occ_xy or not walkable:
        return ()
    clearance = body_clearance_mm(grid)
    reach = BODY_RADIUS_MM + 2 * float(grid.resolution_mm)
    candidates: list[PlannedPose] = []
    for i, j in walkable:
        x_mm, y_mm = grid.cell_center(i, j)
        dist = min_occupied_distance_mm(x_mm, y_mm, occ_xy)
        if dist < clearance or dist > reach:
            continue
        heading = _heading_brush_toward_occupied(grid, x_mm, y_mm, occ_xy)
        if heading is None:
            continue
        left, right = side_brush_points(x_mm, y_mm, heading)
        if not (
            brush_touches_occupied(grid, left) or brush_touches_occupied(grid, right)
        ):
            continue
        if not body_clears_occupied(grid, x_mm, y_mm):
            continue
        candidates.append(
            PlannedPose(x_mm=x_mm, y_mm=y_mm, heading_deg=heading, cell=(i, j))
        )
    if not candidates:
        return ()
    cx = sum(p[0] for p in occ_xy) / len(occ_xy)
    cy = sum(p[1] for p in occ_xy) / len(occ_xy)
    candidates.sort(
        key=lambda p: math.atan2(p.y_mm - cy, p.x_mm - cx)
    )
    return tuple(candidates)
