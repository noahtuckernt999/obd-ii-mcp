from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from obd_ii_mcp.config import Settings
from obd_ii_mcp.dtc import decode_code, parse_dtc_response
from obd_ii_mcp.elm327 import Elm327Protocol
from obd_ii_mcp.errors import NoAdapterFoundError, NoEcuResponseError, ObdError
from obd_ii_mcp.models import (
    CodeReadResult,
    ConnectResult,
    ConnectionStatus,
    DataSeries,
    DecodedCode,
    FaultSnapshot,
    LiveDataResult,
    PortCandidate,
    SampleResult,
    SeriesPoint,
)
from obd_ii_mcp.pids import PID_DEFINITIONS, decode_pid_response, normalize_pid
from obd_ii_mcp.sessions import write_session
from obd_ii_mcp.transport import SerialTransport, Transport, list_serial_ports, select_candidate_ports

TransportFactory = Callable[[str, int, float], Transport]


class ObdService:
    def __init__(
        self,
        settings: Settings,
        transport_factory: TransportFactory | None = None,
        port_lister: Callable[[], list[PortCandidate]] = list_serial_ports,
    ) -> None:
        self.settings = settings
        self.transport_factory = transport_factory or (
            lambda port, baud, timeout: SerialTransport(port, baud, timeout)
        )
        self.port_lister = port_lister
        self.transport: Transport | None = None
        self.protocol: Elm327Protocol | None = None
        self.vin: str | None = None

    def status(self) -> ConnectionStatus:
        return ConnectionStatus(
            connected=self.protocol is not None,
            port=self.transport.port if self.transport else None,
            baud_rate=self.transport.baud_rate if self.transport else None,
            adapter_id=self.protocol.adapter_id if self.protocol else None,
            protocol=self.protocol.protocol if self.protocol else None,
            vin=self.vin,
            vehicle_profile=self.settings.vehicle_profile,
        )

    def connect(self) -> ConnectResult:
        discovered = self.port_lister()
        candidates = select_candidate_ports(self.settings.serial_ports, discovered)
        for candidate in candidates:
            for baud_rate in self.settings.baud_rates:
                transport = self.transport_factory(
                    candidate.device,
                    baud_rate,
                    self.settings.timeout_seconds,
                )
                protocol = Elm327Protocol(transport)
                try:
                    transport.open()
                    protocol.initialize()
                except Exception:
                    transport.close()
                    continue
                self.transport = transport
                self.protocol = protocol
                return ConnectResult(ok=True, status=self.status(), candidates=candidates)
        raise NoAdapterFoundError("No ELM327-compatible adapter responded on candidate COM ports")

    def ensure_connected(self) -> Elm327Protocol:
        if self.protocol is None:
            self.connect()
        assert self.protocol is not None
        return self.protocol

    def read_codes(self) -> CodeReadResult:
        protocol = self.ensure_connected()
        return CodeReadResult(
            ok=True,
            stored=self._read_dtc_mode(protocol, "03", "43"),
            pending=self._read_dtc_mode(protocol, "07", "47"),
            permanent=self._read_dtc_mode(protocol, "0A", "4A"),
        )

    def decode_code(self, code: str) -> DecodedCode:
        return decode_code(code)

    def live_data(self, pids: list[str] | None = None) -> LiveDataResult:
        protocol = self.ensure_connected()
        selected = pids or ["0C", "0D", "05", "0F", "11", "42"]
        values = []
        for pid in selected:
            normalized = normalize_pid(pid)
            response = protocol.obd_query("01", normalized)
            values.append(decode_pid_response(normalized, response))
        return LiveDataResult(ok=True, values=values)

    def sample_data(
        self,
        pids: list[str] | None = None,
        duration_seconds: float = 10,
        interval_seconds: float = 1,
    ) -> SampleResult:
        selected = [normalize_pid(pid) for pid in (pids or ["0C", "0D", "05"])]
        started_at = datetime.now()
        series = {
            pid: DataSeries(
                pid=definition.pid,
                name=definition.name,
                label=definition.label,
                unit=definition.unit,
                points=[],
            )
            for pid, definition in ((pid, PID_DEFINITIONS[pid]) for pid in selected)
        }
        deadline = time.monotonic() + max(duration_seconds, 0)
        first = True
        while first or time.monotonic() < deadline:
            first = False
            timestamp = datetime.now()
            values = self.live_data(selected).values
            for value in values:
                series[value.pid].points.append(SeriesPoint(timestamp=timestamp, value=value.value))
            if time.monotonic() < deadline:
                time.sleep(max(interval_seconds, 0.1))
        finished_at = datetime.now()
        return SampleResult(
            ok=True,
            started_at=started_at,
            finished_at=finished_at,
            interval_seconds=interval_seconds,
            series=list(series.values()),
        )

    def fault_snapshot(self, pids: list[str] | None = None) -> FaultSnapshot:
        captured_at = datetime.now()
        codes = self.read_codes()
        live_data = self.live_data(pids)
        snapshot = FaultSnapshot(
            ok=True,
            captured_at=captured_at,
            status=self.status(),
            codes=codes,
            live_data=live_data,
        )
        path = write_session(self.settings.session_dir, "fault-snapshot", snapshot.model_dump())
        snapshot.session_file = str(path)
        return snapshot

    def read_vin(self) -> str:
        protocol = self.ensure_connected()
        lines = protocol.obd_query("09", "02")
        values: list[int] = []
        for line in lines:
            parts = [int(token, 16) for token in line.split()]
            if 0x49 in parts:
                start = parts.index(0x49)
                values.extend(parts[start + 3 :])
        vin = bytes(value for value in values if 32 <= value <= 126).decode("ascii", errors="ignore")
        self.vin = vin or None
        if self.vin is None:
            raise NoEcuResponseError("VIN response did not contain readable VIN data")
        return self.vin

    def _read_dtc_mode(self, protocol: Elm327Protocol, mode: str, response_mode: str):
        try:
            return parse_dtc_response(protocol.obd_query(mode), response_mode)
        except NoEcuResponseError:
            return []


def result_or_error(fn):
    try:
        result = fn()
    except ObdError as error:
        return error.as_dict()
    return result.model_dump() if hasattr(result, "model_dump") else result
