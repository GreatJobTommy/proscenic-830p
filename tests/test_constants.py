from proscenic_830p.constants import (
    CLIMB_ADVERTISED_MM,
    CLIMB_CONSERVATIVE_MM,
    can_climb,
)


def test_climb_conservative_10_advertised_15() -> None:
    assert CLIMB_CONSERVATIVE_MM == 10
    assert CLIMB_ADVERTISED_MM == 15
    assert can_climb(10) is True
    assert can_climb(11) is False
    assert can_climb(15) is False
