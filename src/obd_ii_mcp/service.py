from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime

from obd_ii_mcp.config import Settings
from obd_ii_mcp.dtc import decode_code, parse_dtc_response
from obd_ii_mcp.elm327 import Elm327Protocol
from obd_ii_mcp.errors import (
    NoAdapterFoundError,
    NoEcuResponseError,
    ObdError,
    UnsupportedDataIdentifierError,
    UnsupportedEcuHeaderError,
)
from obd_ii_mcp.models import (
    CodeReadResult,
    ConnectResult,
    ConnectionStatus,
    DataSeries,
    DataIdentifierReadResult,
    DecodedCode,
    EnhancedProtocolProbe,
    FaultSnapshot,
    LiveDataCapture,
    LiveDataResult,
    PortCandidate,
    ProtocolProbeStep,
    SampleResult,
    SeriesPoint,
)
from obd_ii_mcp.pids import PID_DEFINITIONS, decode_pid_response, normalize_pid
from obd_ii_mcp.replay import LiveDataReplay
from obd_ii_mcp.sessions import write_session
from obd_ii_mcp.transport import SerialTransport, Transport, list_serial_ports, select_candidate_ports

TransportFactory = Callable[[str, int, float], Transport]

READ_ONLY_DIDS = {
    "F187": "Vehicle manufacturer spare part number",
    "F188": "ECU software number",
    "F189": "ECU software version",
    "F18A": "System supplier identifier",
    "F18B": "ECU manufacturing date",
    "F18C": "ECU serial number",
    "F191": "ECU hardware number",
    "F190": "Vehicle identification number",
}

READ_ONLY_ECU_HEADERS = {
    "7E0": "Engine ECU",
}


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
        self.replay: LiveDataReplay | None = None
        self.vin: str | None = None

    def status(self) -> ConnectionStatus:
        if self.replay is not None:
            return ConnectionStatus(
                connected=True,
                port=str(self.settings.replay_file) if self.settings.replay_file else "replay",
                baud_rate=None,
                adapter_id="OBD-II replay",
                protocol="replay",
                vin=self.vin,
                vehicle_profile=self.settings.vehicle_profile,
            )
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
        if self.settings.replay_file is not None:
            self.replay = LiveDataReplay.from_file(self.settings.replay_file)
            return ConnectResult(ok=True, status=self.status(), candidates=[])

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
        if self.settings.replay_file is not None:
            if self.replay is None:
                self.connect()
            return CodeReadResult(ok=True)
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
        if self.settings.replay_file is not None:
            if self.replay is None:
                self.connect()
            assert self.replay is not None
            return self.replay.live_data(pids)

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

    def record_live_data(
        self,
        pids: list[str] | None = None,
        duration_seconds: float = 30,
        interval_seconds: float = 1,
    ) -> LiveDataCapture:
        sample = self.sample_data(pids, duration_seconds, interval_seconds)
        capture = LiveDataCapture(
            ok=True,
            captured_at=datetime.now(),
            status=self.status(),
            sample=sample,
        )
        path = write_session(self.settings.capture_dir, "live-data", capture.model_dump())
        capture.capture_file = str(path)
        path.write_text(capture.model_dump_json(indent=2), encoding="utf-8")
        return capture

    def probe_enhanced_protocols(self) -> EnhancedProtocolProbe:
        protocol = self.ensure_connected()
        steps: list[ProtocolProbeStep] = []

        adapter_protocol = _adapter_value(protocol, "ATDP", steps, "adapter_protocol")
        adapter_protocol_number = _adapter_value(
            protocol,
            "ATDPN",
            steps,
            "adapter_protocol_number",
        )
        can_status = _adapter_value(protocol, "ATCS", steps, "can_status")
        protocol_number = _normalize_protocol_number(adapter_protocol_number)
        protocol_text = (adapter_protocol or "").upper()
        uds_possible = "CAN" in protocol_text or protocol_number in {"6", "7", "8", "9"}
        kwp_possible = "KWP" in protocol_text or protocol_number in {"4", "5"}

        if uds_possible:
            steps.extend(self._probe_uds_read_only(protocol))
        else:
            steps.append(
                ProtocolProbeStep(
                    name="uds_vin_read",
                    ok=False,
                    request="22 F1 90",
                    error="Skipped because the active adapter protocol does not look like ISO 15765-4 CAN",
                )
            )

        if kwp_possible:
            steps.append(
                ProtocolProbeStep(
                    name="kwp_read_only_candidate",
                    ok=True,
                    value="Active protocol looks KWP-capable; add fixed KWP identity reads next",
                )
            )
        else:
            steps.append(
                ProtocolProbeStep(
                    name="kwp_read_only_candidate",
                    ok=False,
                    error="Skipped because the active adapter protocol does not look like ISO 14230-4 KWP",
                )
            )

        return EnhancedProtocolProbe(
            ok=True,
            status=self.status(),
            adapter_protocol=adapter_protocol,
            adapter_protocol_number=adapter_protocol_number,
            can_status=can_status,
            uds_possible=uds_possible,
            kwp_possible=kwp_possible,
            steps=steps,
        )

    def read_data_identifier(self, did: str = "F190", ecu_header: str = "7E0") -> DataIdentifierReadResult:
        normalized_did = _normalize_did(did)
        normalized_header = _normalize_ecu_header(ecu_header)
        name = READ_ONLY_DIDS[normalized_did]
        protocol = self.ensure_connected()
        request = f"22{normalized_did}"

        try:
            self._prepare_uds_can_session(protocol, normalized_header)
            lines = protocol.command(request)
            negative_response = _extract_negative_uds_response(lines)
            if negative_response is not None:
                return DataIdentifierReadResult(
                    ok=False,
                    did=normalized_did,
                    name=name,
                    ecu_header=normalized_header,
                    request=_format_hex(request),
                    response=lines,
                    negative_response=negative_response,
                    error=f"ECU returned negative UDS response {negative_response}",
                )

            payload = _extract_uds_did_payload(lines, normalized_did)
            value = _ascii_from_payload(payload)
            return DataIdentifierReadResult(
                ok=value is not None,
                did=normalized_did,
                name=name,
                ecu_header=normalized_header,
                request=_format_hex(request),
                response=lines,
                value=value,
                raw_payload=[f"{byte:02X}" for byte in payload],
                error=None if value else f"No positive UDS response for DID {normalized_did}",
            )
        finally:
            try:
                protocol.initialize()
            except Exception:
                pass

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

    def _probe_uds_read_only(self, protocol: Elm327Protocol) -> list[ProtocolProbeStep]:
        steps: list[ProtocolProbeStep] = []
        try:
            self._prepare_uds_can_session(protocol, "7E0", steps)

            lines = protocol.command("22F190")
            vin = _ascii_from_payload(_extract_uds_did_payload(lines, "F190"))
            steps.append(
                ProtocolProbeStep(
                    name="uds_vin_read",
                    ok=vin is not None,
                    request="22 F1 90",
                    response=lines,
                    value=vin,
                    error=None if vin else "No positive UDS response for DID F190",
                )
            )
        except Exception as error:
            steps.append(
                ProtocolProbeStep(
                    name="uds_vin_read",
                    ok=False,
                    request="22 F1 90",
                    error=str(error),
                )
            )
        finally:
            try:
                protocol.initialize()
            except Exception:
                pass
        return steps

    def _prepare_uds_can_session(
        self,
        protocol: Elm327Protocol,
        ecu_header: str,
        steps: list[ProtocolProbeStep] | None = None,
    ) -> None:
        response_header = _response_header_for(ecu_header)
        setup_commands = ["ATAL", "ATH1", "ATCAF1", "ATCFC1", f"ATSH{ecu_header}", f"ATCRA{response_header}"]
        for command in setup_commands:
            if steps is None:
                protocol.adapter_command(command)
            else:
                _adapter_value(protocol, command, steps, f"uds_setup_{command.lower()}")


def _adapter_value(
    protocol: Elm327Protocol,
    command: str,
    steps: list[ProtocolProbeStep],
    name: str,
) -> str | None:
    try:
        lines = protocol.adapter_command(command)
    except Exception as error:
        steps.append(ProtocolProbeStep(name=name, ok=False, request=command, error=str(error)))
        return None
    value = " ".join(lines).strip() or None
    steps.append(ProtocolProbeStep(name=name, ok=True, request=command, response=lines, value=value))
    return value


def _extract_uds_did_payload(lines: list[str], did: str) -> list[int]:
    did_bytes = [int(did[index : index + 2], 16) for index in range(0, len(did), 2)]
    values: list[int] = []
    collecting = False
    for line in lines:
        parts = _uds_frame_parts(line)
        if 0x62 not in parts:
            if collecting:
                values.extend(_uds_consecutive_frame_payload(parts))
            continue
        start = parts.index(0x62)
        if parts[start + 1 : start + 3] != did_bytes:
            continue
        collecting = True
        values.extend(parts[start + 3 :])
    return values


def _uds_frame_parts(line: str) -> list[int]:
    tokens = re.findall(r"[0-9A-Fa-f]+", line)
    if len(tokens) != 1:
        return [int(token, 16) for token in tokens]

    compact = tokens[0].upper()
    if len(compact) % 2 == 1 and len(compact) >= 5:
        tokens = [compact[:3], *[compact[index : index + 2] for index in range(3, len(compact), 2)]]
    else:
        tokens = [compact[index : index + 2] for index in range(0, len(compact), 2)]
    return [int(token, 16) for token in tokens if token]


def _uds_consecutive_frame_payload(parts: list[int]) -> list[int]:
    if parts and parts[0] > 0xFF:
        parts = parts[1:]
    if parts and parts[0] & 0xF0 == 0x20:
        parts = parts[1:]
    return parts


def _normalize_protocol_number(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized.startswith("A"):
        normalized = normalized[1:]
    return normalized or None


def _normalize_did(value: str) -> str:
    normalized = value.strip().upper().replace(" ", "").replace("0X", "")
    if normalized not in READ_ONLY_DIDS:
        supported = ", ".join(sorted(READ_ONLY_DIDS))
        raise UnsupportedDataIdentifierError(
            f"DID {value!r} is not in the read-only allow-list. Supported DIDs: {supported}"
        )
    return normalized


def _normalize_ecu_header(value: str) -> str:
    normalized = value.strip().upper().replace(" ", "").replace("0X", "")
    if normalized not in READ_ONLY_ECU_HEADERS:
        supported = ", ".join(sorted(READ_ONLY_ECU_HEADERS))
        raise UnsupportedEcuHeaderError(
            f"ECU header {value!r} is not in the read-only allow-list. Supported headers: {supported}"
        )
    return normalized


def _response_header_for(ecu_header: str) -> str:
    return f"{int(ecu_header, 16) + 8:03X}"


def _ascii_from_payload(payload: list[int]) -> str | None:
    text = bytes(value for value in payload if 32 <= value <= 126).decode("ascii", errors="ignore")
    return text or None


def _extract_negative_uds_response(lines: list[str]) -> str | None:
    for line in lines:
        parts = _uds_frame_parts(line)
        if 0x7F not in parts:
            continue
        start = parts.index(0x7F)
        response = parts[start : start + 3]
        if len(response) == 3:
            return " ".join(f"{byte:02X}" for byte in response)
    return None


def _format_hex(value: str) -> str:
    compact = value.strip().upper().replace(" ", "")
    return " ".join(compact[index : index + 2] for index in range(0, len(compact), 2))


def result_or_error(fn):
    try:
        result = fn()
    except ObdError as error:
        return error.as_dict()
    return result.model_dump() if hasattr(result, "model_dump") else result
