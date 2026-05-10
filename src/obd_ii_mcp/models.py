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


class DisconnectResult(BaseModel):
    ok: bool
    status: ConnectionStatus
    released: bool


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


class SupportedPid(BaseModel):
    mode: str = "01"
    pid: str
    supported: bool = True
    decoded: bool
    name: str | None = None
    label: str
    unit: str | None = None
    group: str = "Other"


class PidDiscoveryResult(BaseModel):
    ok: bool
    status: ConnectionStatus
    source: str
    supported: list[SupportedPid]
    decoded: list[SupportedPid]
    undecoded: list[SupportedPid]


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


class LiveDataCapture(BaseModel):
    ok: bool
    capture_file: str | None = None
    captured_at: datetime
    status: ConnectionStatus
    sample: SampleResult


class ProtocolProbeStep(BaseModel):
    name: str
    ok: bool
    request: str | None = None
    response: list[str] = Field(default_factory=list)
    value: str | None = None
    error: str | None = None


class EnhancedProtocolProbe(BaseModel):
    ok: bool
    status: ConnectionStatus
    adapter_protocol: str | None = None
    adapter_protocol_number: str | None = None
    can_status: str | None = None
    uds_possible: bool
    kwp_possible: bool
    steps: list[ProtocolProbeStep] = Field(default_factory=list)


class DataIdentifierReadResult(BaseModel):
    ok: bool
    did: str
    name: str
    ecu_header: str
    request: str
    response: list[str] = Field(default_factory=list)
    value: str | None = None
    raw_payload: list[str] = Field(default_factory=list)
    negative_response: str | None = None
    error: str | None = None


class FaultSnapshot(BaseModel):
    ok: bool
    captured_at: datetime
    status: ConnectionStatus
    codes: CodeReadResult
    live_data: LiveDataResult
    session_file: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
