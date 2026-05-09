from pathlib import Path

from obd_ii_mcp.config import load_settings


def test_config_defaults() -> None:
    settings = load_settings({})
    assert settings.serial_ports == []
    assert settings.baud_rates == [38400, 9600]
    assert settings.read_timeout_ms == 2000
    assert settings.session_dir == Path(".obd-mcp/sessions")
    assert settings.vehicle_profile == "generic"


def test_config_env_overrides() -> None:
    settings = load_settings(
        {
            "OBD_MCP_SERIAL_PORTS": "COM4, COM9",
            "OBD_MCP_BAUD_RATES": "115200,38400",
            "OBD_MCP_READ_TIMEOUT_MS": "500",
            "OBD_MCP_SESSION_DIR": "captures",
            "OBD_MCP_VEHICLE_PROFILE": "vag",
        }
    )
    assert settings.serial_ports == ["COM4", "COM9"]
    assert settings.baud_rates == [115200, 38400]
    assert settings.read_timeout_ms == 500
    assert settings.session_dir == Path("captures")
    assert settings.vehicle_profile == "vag"
