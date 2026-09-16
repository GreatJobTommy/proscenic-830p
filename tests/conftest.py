from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def occupancy_trace_path() -> Path:
    return FIXTURES / "occupancy_trace.json"


@pytest.fixture
def occupancy_trace(occupancy_trace_path: Path) -> dict:
    import json

    return json.loads(occupancy_trace_path.read_text(encoding="utf-8"))


@pytest.fixture
def dps_payloads() -> dict:
    import json

    return json.loads((FIXTURES / "dps_payloads.json").read_text(encoding="utf-8"))
