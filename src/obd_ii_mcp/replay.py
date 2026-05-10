from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from obd_ii_mcp.models import DataSeries, LiveDataCapture, LiveDataResult, LiveValue
from obd_ii_mcp.pids import PID_DEFINITIONS, normalize_pid


class LiveDataReplay:
    def __init__(self, capture: LiveDataCapture) -> None:
        self.capture = capture
        self.started_at = datetime.now()

    @classmethod
    def from_file(cls, path: Path) -> LiveDataReplay:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(LiveDataCapture.model_validate(payload))

    def live_data(self, pids: list[str] | None = None) -> LiveDataResult:
        series_by_pid = {series.pid: series for series in self.capture.sample.series}
        selected = [normalize_pid(pid) for pid in pids] if pids else list(series_by_pid)
        elapsed = (datetime.now() - self.started_at).total_seconds()
        duration = max(
            (self.capture.sample.finished_at - self.capture.sample.started_at).total_seconds(),
            self.capture.sample.interval_seconds,
            0.1,
        )
        offset = elapsed % duration

        values = []
        for pid in selected:
            series = series_by_pid[pid]
            value = _value_at_offset(series, self.capture.sample.started_at, offset)
            definition = PID_DEFINITIONS[pid]
            values.append(
                LiveValue(
                    pid=definition.pid,
                    name=definition.name,
                    label=definition.label,
                    value=value,
                    unit=definition.unit,
                )
            )
        return LiveDataResult(ok=True, values=values)


def _value_at_offset(series: DataSeries, started_at: datetime, offset: float):
    nearest = min(
        series.points,
        key=lambda point: abs((point.timestamp - started_at).total_seconds() - offset),
    )
    return nearest.value
