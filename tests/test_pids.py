import pytest

from obd_ii_mcp.errors import MalformedResponseError, UnsupportedPidError
from obd_ii_mcp.pids import (
    decode_pid_response,
    normalize_pid,
    pid_group,
    standard_pid_label,
)


@pytest.mark.parametrize(
    ("pid", "response", "expected", "unit"),
    [
        ("04", "41 04 80", 50.196, "%"),
        ("11", "41 11 FF", 100.0, "%"),
        ("2E", "41 2E 40", 25.098, "%"),
        ("2F", "41 2F C0", 75.294, "%"),
        ("45", "41 45 00", 0.0, "%"),
        ("47", "41 47 7F", 49.804, "%"),
        ("48", "41 48 80", 50.196, "%"),
        ("49", "41 49 FF", 100.0, "%"),
        ("4A", "41 4A 20", 12.549, "%"),
        ("4C", "41 4C A0", 62.745, "%"),
    ],
)
def test_decode_percent_pids(pid: str, response: str, expected: float, unit: str) -> None:
    value = decode_pid_response(pid, [response])
    assert value.value == expected
    assert value.unit == unit


@pytest.mark.parametrize(
    ("pid", "response", "expected", "unit"),
    [
        ("05", "41 05 7B", 83, "degC"),
        ("0F", "41 0F 32", 10, "degC"),
        ("46", "41 46 50", 40, "degC"),
        ("3C", "41 3C 01 F4", 10.0, "degC"),
    ],
)
def test_decode_temperature_pids(pid: str, response: str, expected: float, unit: str) -> None:
    value = decode_pid_response(pid, [response])
    assert value.value == expected
    assert value.unit == unit


@pytest.mark.parametrize(
    ("pid", "response", "expected", "unit"),
    [
        ("0B", "41 0B 64", 100.0, "kPa"),
        ("0C", "41 0C 1A F8", 1726, "rpm"),
        ("0D", "41 0D 3C", 60.0, "km/h"),
        ("0E", "41 0E 80", 0, "degrees"),
        ("14", "41 14 80 00", 0.64, "V"),
        ("15", "41 15 40 80", 0.32, "V"),
        ("1F", "41 1F 00 0A", 10, "s"),
        ("21", "41 21 01 00", 256, "km"),
        ("23", "41 23 00 0A", 100, "kPa"),
        ("30", "41 30 05", 5.0, "count"),
        ("31", "41 31 00 FF", 255, "km"),
        ("33", "41 33 65", 101.0, "kPa"),
        ("42", "41 42 2E E0", 12.0, "V"),
        ("43", "41 43 01 00", 100.392, "%"),
        ("44", "41 44 40 00", 0.5, "ratio"),
    ],
)
def test_decode_numeric_pids(pid: str, response: str, expected: float, unit: str) -> None:
    value = decode_pid_response(pid, [response])
    assert value.value == expected
    assert value.unit == unit


@pytest.mark.parametrize(
    ("pid", "response", "expected", "unit"),
    [
        ("06", "41 06 90", 12.5, "%"),
        ("07", "41 07 70", -12.5, "%"),
        ("56", "41 56 90 70", "bank 1 12.5%; bank 3 -12.5%", ""),
    ],
)
def test_decode_fuel_trim_pids(pid: str, response: str, expected: float | str, unit: str) -> None:
    value = decode_pid_response(pid, [response])
    assert value.value == expected
    assert value.unit == unit


@pytest.mark.parametrize(
    ("pid", "response", "expected"),
    [
        ("01", "41 01 82 00 00 00", "MIL on; 2 stored DTCs"),
        (
            "03",
            "41 03 02 00",
            "system 1: Closed loop using oxygen sensor feedback; system 2: Not used",
        ),
        ("03", "41 03 99 01", "system 1: Status 0x99; system 2: Open loop due to insufficient engine temperature"),
        ("13", "41 13 05", "O2S1, O2S3"),
        ("13", "41 13 00", "None"),
        ("1C", "41 1C 06", "EOBD"),
        ("1C", "41 1C FE", "Standard 0xFE"),
        ("41", "41 41 01 02 03 04", "raw monitor bitmask 01 02 03 04"),
        ("4F", "41 4F 80 64 05 0A", "equivalence ratio 0.502; O2 voltage 0.500 V; O2 current 5 mA; intake pressure 100 kPa"),
        ("50", "41 50 00 64 0A 14", "MAF 1000 g/s; air flow from MAP 100 g/s; absolute pressure 200 kPa"),
        ("51", "41 51 04", "Diesel"),
        ("51", "41 51 FE", "Fuel type 0xFE"),
    ],
)
def test_decode_text_pids(pid: str, response: str, expected: str) -> None:
    value = decode_pid_response(pid, [response])
    assert value.value == expected
    assert value.unit == ""


@pytest.mark.parametrize(
    ("pid", "response", "expected"),
    [
        ("20", "41 20 80 00 00 01", "21, 40"),
        ("40", "41 40 80 00 00 01", "41, 60"),
        ("60", "41 60 80 00 00 01", "61, 80"),
        ("20", "41 20 00 00 00 00", "None"),
    ],
)
def test_decode_supported_pid_markers(pid: str, response: str, expected: str) -> None:
    value = decode_pid_response(pid, [response])
    assert value.value == expected
    assert value.unit == ""


def test_decode_raw_fallback_pid_70() -> None:
    value = decode_pid_response("70", ["41 70 DE AD BE EF"])
    assert value.value == "DE AD BE EF"
    assert value.unit == ""


@pytest.mark.parametrize(
    ("alias", "normalized"),
    [
        ("coolant", "05"),
        ("rpm", "0C"),
        ("speed", "0D"),
        ("stft_b1", "06"),
        ("o2s2", "15"),
        ("fuel_level", "2F"),
        ("baro", "33"),
        ("voltage", "42"),
        ("0x42", "42"),
    ],
)
def test_normalize_pid_aliases(alias: str, normalized: str) -> None:
    assert normalize_pid(alias) == normalized


def test_pid_metadata_helpers_use_definitions_and_fallbacks() -> None:
    assert pid_group("0C") == "Engine"
    assert standard_pid_label("0C") == "Engine RPM"
    assert standard_pid_label("52") == "Ethanol fuel percentage"
    assert standard_pid_label("AA") == "PID AA"


def test_decode_finds_matching_response_among_other_frames() -> None:
    value = decode_pid_response("0C", ["41 0D 00", "7E8 06 41 0C 0A 2E 00 00"])
    assert value.value == 651.5


@pytest.mark.parametrize(
    ("pid", "response"),
    [
        ("04", "41 04"),
        ("0C", "41 0C 1A"),
        ("01", "41 01 82 00 00"),
        ("20", "41 20 80 00 00"),
        ("70", "41 70 DE AD BE"),
    ],
)
def test_malformed_short_pid_responses_raise(pid: str, response: str) -> None:
    with pytest.raises(MalformedResponseError):
        decode_pid_response(pid, [response])


def test_malformed_response_without_matching_pid_raises() -> None:
    with pytest.raises(MalformedResponseError):
        decode_pid_response("0C", ["41 0D 1A F8"])


def test_unknown_pid_raises() -> None:
    with pytest.raises(UnsupportedPidError):
        normalize_pid("FF")
