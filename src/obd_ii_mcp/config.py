from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _csv_ints(value: str | None, default: list[int]) -> list[int]:
    values = _csv(value)
    if not values:
        return default
    return [int(value) for value in values]


class Settings(BaseModel):
    serial_ports: list[str] = Field(default_factory=list)
    baud_rates: list[int] = Field(default_factory=lambda: [38400, 9600])
    read_timeout_ms: int = 2000
    session_dir: Path = Path(".obd-mcp/sessions")
    capture_dir: Path = Path(".obd-mcp/captures")
    replay_file: Path | None = None
    vehicle_profile: str = "generic"

    @property
    def timeout_seconds(self) -> float:
        return self.read_timeout_ms / 1000


def load_settings(env: dict[str, str] | None = None) -> Settings:
    source = env if env is not None else os.environ
    return Settings(
        serial_ports=_csv(source.get("OBD_MCP_SERIAL_PORTS")),
        baud_rates=_csv_ints(source.get("OBD_MCP_BAUD_RATES"), [38400, 9600]),
        read_timeout_ms=int(source.get("OBD_MCP_READ_TIMEOUT_MS", "2000")),
        session_dir=Path(source.get("OBD_MCP_SESSION_DIR", ".obd-mcp/sessions")),
        capture_dir=Path(source.get("OBD_MCP_CAPTURE_DIR", ".obd-mcp/captures")),
        replay_file=Path(source["OBD_MCP_REPLAY_FILE"]) if source.get("OBD_MCP_REPLAY_FILE") else None,
        vehicle_profile=source.get("OBD_MCP_VEHICLE_PROFILE", "generic"),
    )
