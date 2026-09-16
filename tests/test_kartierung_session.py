from proscenic_830p.kartierung_session import KartierungSession
from proscenic_830p.map_image import render_occupancy_png
from proscenic_830p.protocol import Fault, VacuumStatus, WorkState


def _status(*, hit: bool = False) -> VacuumStatus:
    return VacuumStatus(
        battery=100,
        work_state=WorkState.REMOTE,
        fan=None,
        faults=Fault.COLLISION_SENSOR if hit else Fault.NO_ERROR,
        mop_equipped=False,
        cleaned_area=None,
        clean_time_min=None,
        raw={},
    )


def test_session_start_marks_dock_and_png_is_png() -> None:
    session = KartierungSession()
    session.start()
    assert session.running is True
    assert session.grid.dock_pose is not None
    assert session.grid.report().dock_cells
    png = render_occupancy_png(session.grid, pose=session.pose)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 200


def test_first_tick_without_bumper_drives_forward() -> None:
    session = KartierungSession()
    session.start()
    dps = session.tick(_status(hit=False), dt_s=0.2)
    assert dps == {"26": "forward"}
    assert session.phase == "explore"


def test_bumper_hit_backs_off_and_stamps_occupied() -> None:
    session = KartierungSession()
    session.start()
    session.tick(_status(hit=False), dt_s=0.2)
    dps = session.tick(_status(hit=True), dt_s=0.2)
    assert dps == {"26": "backward"}
    assert session.grid.report().occupied > 0
    assert session.phase == "backoff"


def test_stop_halts_session() -> None:
    session = KartierungSession()
    session.start()
    session.stop()
    assert session.running is False
    assert session.tick(_status(), dt_s=0.2) == {"26": "stop"}
