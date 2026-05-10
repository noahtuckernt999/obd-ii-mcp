from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from obd_ii_mcp.errors import AdapterTimeoutError
from obd_ii_mcp.models import PortCandidate


class Transport(Protocol):
    port: str
    baud_rate: int

    def open(self) -> None: ...
    def close(self) -> None: ...
    def command(self, command: str) -> str: ...


@dataclass
class SerialTransport:
    port: str
    baud_rate: int
    timeout_seconds: float
    _serial: object | None = None

    def open(self) -> None:
        import serial

        self._serial = serial.Serial(
            self.port,
            self.baud_rate,
            timeout=self.timeout_seconds,
            write_timeout=self.timeout_seconds,
        )

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def command(self, command: str) -> str:
        if self._serial is None:
            self.open()
        assert self._serial is not None
        serial_port = self._serial
        serial_port.reset_input_buffer()
        serial_port.write(f"{command}\r".encode("ascii"))
        serial_port.flush()

        deadline = time.monotonic() + self.timeout_seconds
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            chunk = serial_port.read(1)
            if chunk:
                chunks.append(chunk)
                if chunk == b">":
                    return b"".join(chunks).decode("ascii", errors="replace")
        raise AdapterTimeoutError(f"Timed out waiting for adapter response to {command!r}")


@dataclass
class FakeTransport:
    port: str
    baud_rate: int
    responses: dict[str, str]
    opened: bool = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def command(self, command: str) -> str:
        self.opened = True
        key = command.upper().replace(" ", "")
        if key not in self.responses:
            return "NO DATA\r>"
        return self.responses[key]


def list_serial_ports() -> list[PortCandidate]:
    from serial.tools import list_ports

    return [
        PortCandidate(
            device=port.device,
            description=port.description or "",
            manufacturer=port.manufacturer or "",
        )
        for port in list_ports.comports()
    ]


def select_candidate_ports(preferred: list[str], discovered: list[PortCandidate]) -> list[PortCandidate]:
    if preferred:
        by_device = {port.device.upper(): port for port in discovered}
        return [
            by_device.get(name.upper(), PortCandidate(device=name, description="configured"))
            for name in preferred
        ]

    candidates: list[PortCandidate] = []
    for port in discovered:
        text = f"{port.device} {port.description} {port.manufacturer}".lower()
        if "intel" in text and "management" in text:
            continue
        if "bluetooth" in text or port.device.upper().startswith("COM"):
            candidates.append(port)
    return candidates
