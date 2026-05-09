from __future__ import annotations

import re
from dataclasses import dataclass

from obd_ii_mcp.errors import MalformedResponseError, NoEcuResponseError
from obd_ii_mcp.transport import Transport

NO_DATA_MARKERS = {"NO DATA", "UNABLE TO CONNECT", "STOPPED", "CAN ERROR", "BUS ERROR"}


def clean_response(raw: str, command: str | None = None) -> list[str]:
    command_text = command.upper().replace(" ", "") if command else None
    text = raw.replace("\r", "\n").replace(">", "\n")
    lines: list[str] = []
    for line in text.splitlines():
        value = line.strip()
        if not value:
            continue
        compact = value.upper().replace(" ", "")
        if command_text and compact == command_text:
            continue
        if value.upper() == "SEARCHING...":
            continue
        lines.append(value)
    return lines


def normalize_hex_lines(lines: list[str]) -> list[str]:
    hex_lines: list[str] = []
    for line in lines:
        if any(marker in line.upper() for marker in NO_DATA_MARKERS):
            raise NoEcuResponseError(line)
        tokens = re.findall(r"[0-9A-Fa-f]{2}", line)
        if tokens:
            hex_lines.append(" ".join(token.upper() for token in tokens))
    if not hex_lines:
        raise MalformedResponseError("Response did not contain hex data")
    return hex_lines


@dataclass
class Elm327Protocol:
    transport: Transport
    adapter_id: str | None = None
    protocol: str | None = None

    def command(self, command: str) -> list[str]:
        return clean_response(self.transport.command(command), command)

    def adapter_command(self, command: str) -> list[str]:
        lines = self.command(command)
        if not lines or any(marker in line.upper() for marker in NO_DATA_MARKERS for line in lines):
            raise MalformedResponseError(f"Adapter command {command!r} did not return a valid response")
        return lines

    def initialize(self) -> None:
        reset_lines = self.adapter_command("ATZ")
        self.adapter_command("ATE0")
        self.adapter_command("ATL0")
        self.adapter_command("ATS0")
        self.adapter_command("ATH0")
        id_lines = self.adapter_command("ATI")
        self.adapter_command("ATSP0")
        self.adapter_id = " ".join(id_lines or reset_lines).strip() or None
        try:
            self.protocol = " ".join(self.command("ATDP")).strip() or None
        except Exception:
            self.protocol = "AUTO"

    def obd_query(self, mode: str, pid: str | None = None) -> list[str]:
        command = mode if pid is None else f"{mode}{pid}"
        return normalize_hex_lines(self.command(command))
