from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from obd_ii_mcp.dashboard import (
    _capture_name_from_path,
    _capture_prefix,
    _capture_samples,
    _chart_rows,
    _latest_elapsed_seconds,
    _rename_capture,
    _trim_samples,
)
from obd_ii_mcp.models import (
    ConnectionStatus,
    DataSeries,
    LiveDataCapture,
    SampleResult,
    SeriesPoint,
)
import obd_ii_mcp.dashboard as dashboard


def make_capture(path: Path) -> Path:
    started_at = datetime(2026, 5, 10, 12, 0, 0)
    capture = LiveDataCapture(
        ok=True,
        captured_at=started_at,
        status=ConnectionStatus(
            connected=True,
            port="COM4",
            baud_rate=38400,
            adapter_id="ELM327 v1.5",
            protocol="AUTO",
        ),
        sample=SampleResult(
            ok=True,
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=2),
            interval_seconds=1,
            series=[
                DataSeries(
                    pid="42",
                    name="control_module_voltage",
                    label="Control module voltage",
                    unit="V",
                    points=[
                        SeriesPoint(timestamp=started_at, value=12.1),
                        SeriesPoint(timestamp=started_at + timedelta(seconds=2), value=12.3),
                    ],
                ),
                DataSeries(
                    pid="51",
                    name="fuel_type",
                    label="Fuel type",
                    unit="",
                    points=[SeriesPoint(timestamp=started_at + timedelta(seconds=1), value="Diesel")],
                ),
            ],
        ),
    )
    path.write_text(capture.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_capture_prefix_slugifies_names() -> None:
    assert _capture_prefix("  12V Load Test!  ") == "live-data-12v-load-test"
    assert _capture_prefix("") == "live-data"


def test_capture_name_from_timestamped_path() -> None:
    assert (
        _capture_name_from_path(r".obd-mcp\captures\20260510-190936-live-data-12v-load-test.json")
        == "12v load test"
    )
    assert _capture_name_from_path("capture.json") == ""


def test_capture_samples_flattens_series_and_elapsed_seconds(tmp_path: Path) -> None:
    capture_path = make_capture(tmp_path / "20260510-120000-live-data-test.json")

    samples = _capture_samples(str(capture_path))

    assert [sample["pid"] for sample in samples] == ["42", "51", "42"]
    assert [sample["elapsed_seconds"] for sample in samples] == [0.0, 1.0, 2.0]
    assert samples[1]["value"] == "Diesel"


def test_chart_rows_include_only_selected_numeric_samples() -> None:
    samples = [
        {"elapsed_seconds": 0, "pid": "42", "label": "Voltage", "value": 12.1},
        {"elapsed_seconds": 1, "pid": "51", "label": "Fuel type", "value": "Diesel"},
        {"elapsed_seconds": 2, "pid": "05", "label": "Coolant", "value": 83},
    ]

    assert _chart_rows(samples, ["42", "51"]) == [
        {"seconds": 0, "signal": "Voltage", "value": 12.1}
    ]


def test_rename_capture_updates_slug_and_rejects_duplicates(tmp_path: Path) -> None:
    current = make_capture(tmp_path / "20260510-120000-live-data-old-name.json")
    duplicate = make_capture(tmp_path / "20260510-120000-live-data-new-name.json")

    with pytest.raises(ValueError, match="already exists"):
        _rename_capture(str(current), "new name")

    duplicate.unlink()
    renamed = Path(_rename_capture(str(current), "new name"))

    assert renamed.name == "20260510-120000-live-data-new-name.json"
    assert renamed.exists()
    assert not current.exists()


def test_trim_samples_uses_selected_pid_count(monkeypatch: pytest.MonkeyPatch) -> None:
    state = SimpleNamespace(samples=[{"pid": "42", "value": index} for index in range(10)])
    monkeypatch.setattr(dashboard.st, "session_state", state)

    _trim_samples(max_points=3, selected_pids=["42", "05"])

    assert [sample["value"] for sample in state.samples] == [4, 5, 6, 7, 8, 9]


def test_latest_elapsed_seconds_reads_session_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dashboard.st,
        "session_state",
        SimpleNamespace(samples=[{"elapsed_seconds": 0.25}, {"elapsed_seconds": 3.5}]),
    )

    assert _latest_elapsed_seconds() == 3.5
