from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_states_830p_vs_790t_and_local_limits() -> None:
    text = README.read_text(encoding="utf-8")
    assert "6668" in text
    assert "Tuya" in text
    assert "790T" in text
    assert "robotbona" in text.lower()
    assert "local_key" in text
    assert "device_id" in text
    assert "2.4" in text
    assert "1.0.3" in text
    assert "1.4.3" in text
    assert "gyro" in text.lower()
