from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorResult(BaseModel):
    ok: bool = False
    error: str
    message: str


class PortCandidate(BaseModel):
    device: str
    description: str = ""
    manufacturer: str = ""


class ConnectionStatus(BaseModel):
    connected: bool
    port: str | None = None
    baud_rate: int | None = None
    adapter_id: str | None = None
    protocol: str | None = None
    vin: str | None = None
    vehicle_profile: str = "generic"


class ConnectResult(BaseModel):
    ok: bool
    status: ConnectionStatus
    candidates: list[PortCandidate] = Field(default_factory=list)


class Dtc(BaseModel):
    code: str
    description: str
    raw: str


class CodeReadResult(BaseModel):
    ok: bool
    stored: list[Dtc] = Field(default_factory=list)
    pending: list[Dtc] = Field(default_factory=list)
    permanent: list[Dtc] = Field(default_factory=list)


class DecodedCode(BaseModel):
    ok: bool
    code: str
    description: str
    known: bool
    system: str


class LiveValue(BaseModel):
    mode: str = "01"
    pid: str
    name: str
    label: str
    value: float | str | None
    unit: str
    supported: bool = True


class LiveDataResult(BaseModel):
    ok: bool
    values: list[LiveValue]


class SeriesPoint(BaseModel):
    timestamp: datetime
    value: float | str | None


class DataSeries(BaseModel):
    mode: str = "01"
    pid: str
    name: str
    label: str
    unit: str
    points: list[SeriesPoint]


class SampleResult(BaseModel):
    ok: bool
    started_at: datetime
    finished_at: datetime
    interval_seconds: float
    series: list[DataSeries]


class FaultSnapshot(BaseModel):
    ok: bool
    captured_at: datetime
    status: ConnectionStatus
    codes: CodeReadResult
    live_data: LiveDataResult
    session_file: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
