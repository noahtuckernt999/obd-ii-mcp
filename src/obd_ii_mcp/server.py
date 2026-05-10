from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from obd_ii_mcp.config import load_settings
from obd_ii_mcp.service import ObdService, result_or_error

settings = load_settings()
service = ObdService(settings)
mcp = FastMCP("OBD-II MCP")


@mcp.tool()
def obd_connect() -> dict[str, Any]:
    """Probe Bluetooth serial ports and connect to an ELM327-compatible OBD-II adapter."""
    return result_or_error(service.connect)


@mcp.tool()
def obd_disconnect() -> dict[str, Any]:
    """Close the current adapter or replay session and release the serial port."""
    return result_or_error(service.disconnect)


@mcp.tool()
def obd_status(read_vin: bool = False) -> dict[str, Any]:
    """Return adapter connection status, protocol metadata, and VIN when requested."""
    def action():
        if read_vin:
            service.read_vin()
        return service.status()

    return result_or_error(action)


@mcp.tool()
def obd_read_codes() -> dict[str, Any]:
    """Read stored, pending, and permanent generic OBD-II diagnostic trouble codes."""
    return result_or_error(service.read_codes)


@mcp.tool()
def obd_decode_code(code: str) -> dict[str, Any]:
    """Decode a generic OBD-II diagnostic trouble code."""
    return result_or_error(lambda: service.decode_code(code))


@mcp.tool()
def obd_live_data(pids: list[str] | None = None) -> dict[str, Any]:
    """Read supported live OBD-II PIDs once."""
    return result_or_error(lambda: service.live_data(pids))


@mcp.tool()
def obd_discover_pids() -> dict[str, Any]:
    """Discover which OBD-II mode 01 PIDs the vehicle reports as supported."""
    return result_or_error(service.discover_pids)


@mcp.tool()
def obd_sample_data(
    pids: list[str] | None = None,
    duration_seconds: float = 10,
    interval_seconds: float = 1,
) -> dict[str, Any]:
    """Sample supported live OBD-II PIDs and return graph-ready series data."""
    return result_or_error(lambda: service.sample_data(pids, duration_seconds, interval_seconds))


@mcp.tool()
def obd_record_live_data(
    pids: list[str] | None = None,
    duration_seconds: float = 30,
    interval_seconds: float = 1,
) -> dict[str, Any]:
    """Record live OBD-II PID samples to a replayable local capture file."""
    return result_or_error(lambda: service.record_live_data(pids, duration_seconds, interval_seconds))


@mcp.tool()
def obd_probe_enhanced_protocols() -> dict[str, Any]:
    """Read-only probe for UDS/KWP capability through the current ELM327 adapter session."""
    return result_or_error(service.probe_enhanced_protocols)


@mcp.tool()
def obd_read_data_identifier(did: str = "F190", ecu_header: str = "7E0") -> dict[str, Any]:
    """Read an allow-listed UDS data identifier with service 22."""
    return result_or_error(lambda: service.read_data_identifier(did, ecu_header))


@mcp.tool()
def obd_fault_snapshot(pids: list[str] | None = None) -> dict[str, Any]:
    """Capture DTCs plus relevant live data and persist a local JSON session file."""
    return result_or_error(lambda: service.fault_snapshot(pids))


def main() -> None:
    mcp.run()
