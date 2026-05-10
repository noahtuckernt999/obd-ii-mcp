import pytest

from obd_ii_mcp.errors import MalformedResponseError, UnsupportedPidError
from obd_ii_mcp.pids import decode_pid_response, normalize_pid


def test_decode_rpm() -> None:
    value = decode_pid_response("0C", ["41 0C 1A F8"])
    assert value.value == 1726
    assert value.unit == "rpm"


def test_decode_coolant_temp() -> None:
    value = decode_pid_response("coolant", ["41 05 7B"])
    assert value.value == 83
    assert value.unit == "degC"


def test_decode_voltage() -> None:
    value = decode_pid_response("42", ["41 42 2E E0"])
    assert value.value == 12.0
    assert value.unit == "V"


def test_decode_timing_advance() -> None:
    value = decode_pid_response("0E", ["41 0E 80"])
    assert value.value == 0
    assert value.unit == "degrees"


def test_decode_fuel_type_as_text() -> None:
    value = decode_pid_response("51", ["41 51 04"])
    assert value.value == "Diesel"
    assert value.unit == ""


def test_decode_supported_pid_marker_as_text() -> None:
    value = decode_pid_response("20", ["41 20 80 00 00 01"])
    assert value.value == "21, 40"
    assert value.unit == ""


def test_unknown_pid_raises() -> None:
    with pytest.raises(UnsupportedPidError):
        normalize_pid("FF")


def test_malformed_pid_response_raises() -> None:
    with pytest.raises(MalformedResponseError):
        decode_pid_response("0C", ["41 0C 1A"])
