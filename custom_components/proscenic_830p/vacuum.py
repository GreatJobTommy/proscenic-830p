"""Home Assistant vacuum platform for the Proscenic 830P."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_library() -> None:
    try:
        import proscenic_830p  # noqa: F401
        return
    except ImportError:
        pass
    here = Path(__file__).resolve()
    for candidate in (here.parents[2], here.parent / "vendor"):
        if (candidate / "proscenic_830p").is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            return


_ensure_library()

from proscenic_830p.ha_vacuum import (  # noqa: E402
    PLATFORM_SCHEMA,
    Proscenic830PVacuum,
    async_setup_platform,
    build_vacuum,
)

__all__ = [
    "PLATFORM_SCHEMA",
    "Proscenic830PVacuum",
    "async_setup_platform",
    "build_vacuum",
]
