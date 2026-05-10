from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from obd_ii_mcp.errors import MalformedResponseError, UnsupportedPidError
from obd_ii_mcp.models import LiveValue

Decoder = Callable[[list[int]], float]


@dataclass(frozen=True)
class PidDefinition:
    pid: str
    name: str
    label: str
    unit: str
    byte_count: int
    decoder: Decoder


def _one(transform: Callable[[int], float]) -> Decoder:
    return lambda data: transform(data[0])


def _two(transform: Callable[[int, int], float]) -> Decoder:
    return lambda data: transform(data[0], data[1])


PID_DEFINITIONS: dict[str, PidDefinition] = {
    "04": PidDefinition("04", "calculated_engine_load", "Calculated engine load", "%", 1, _one(lambda a: a * 100 / 255)),
    "05": PidDefinition("05", "coolant_temp", "Engine coolant temperature", "degC", 1, _one(lambda a: a - 40)),
    "0B": PidDefinition("0B", "intake_manifold_pressure", "Intake manifold pressure", "kPa", 1, _one(float)),
    "0C": PidDefinition("0C", "rpm", "Engine RPM", "rpm", 2, _two(lambda a, b: ((a * 256) + b) / 4)),
    "0D": PidDefinition("0D", "vehicle_speed", "Vehicle speed", "km/h", 1, _one(float)),
    "0F": PidDefinition("0F", "intake_air_temp", "Intake air temperature", "degC", 1, _one(lambda a: a - 40)),
    "11": PidDefinition("11", "throttle_position", "Throttle position", "%", 1, _one(lambda a: a * 100 / 255)),
    "06": PidDefinition("06", "short_term_fuel_trim_b1", "Short term fuel trim bank 1", "%", 1, _one(lambda a: (a - 128) * 100 / 128)),
    "07": PidDefinition("07", "long_term_fuel_trim_b1", "Long term fuel trim bank 1", "%", 1, _one(lambda a: (a - 128) * 100 / 128)),
    "14": PidDefinition("14", "oxygen_sensor_1_voltage", "O2 sensor 1 voltage", "V", 2, _two(lambda a, _b: a / 200)),
    "42": PidDefinition("42", "control_module_voltage", "Control module voltage", "V", 2, _two(lambda a, b: ((a * 256) + b) / 1000)),
}

PID_ALIASES = {
    "load": "04",
    "coolant_temp": "05",
    "coolant": "05",
    "map": "0B",
    "rpm": "0C",
    "speed": "0D",
    "vehicle_speed": "0D",
    "intake_air_temp": "0F",
    "iat": "0F",
    "throttle": "11",
    "short_term_fuel_trim_b1": "06",
    "stft_b1": "06",
    "long_term_fuel_trim_b1": "07",
    "ltft_b1": "07",
    "o2s1": "14",
    "voltage": "42",
    "control_module_voltage": "42",
}


def normalize_pid(pid: str) -> str:
    key = pid.strip().lower()
    value = PID_ALIASES.get(key, key)
    normalized = value.upper().replace("0X", "")
    if normalized not in PID_DEFINITIONS:
        raise UnsupportedPidError(f"Unsupported PID {pid!r}")
    return normalized


def decode_pid_response(pid: str, hex_lines: list[str]) -> LiveValue:
    normalized = normalize_pid(pid)
    definition = PID_DEFINITIONS[normalized]
    expected = int(normalized, 16)

    payload: list[int] | None = None
    for line in hex_lines:
        values = [int(token, 16) for token in line.split()]
        for index in range(0, len(values) - 1):
            if values[index] == 0x41 and values[index + 1] == expected:
                payload = values[index + 2 : index + 2 + definition.byte_count]
                break
        if payload is not None:
            break

    if payload is None or len(payload) < definition.byte_count:
        raise MalformedResponseError(f"PID {normalized} response did not include enough data")

    value = definition.decoder(payload)
    return LiveValue(
        pid=definition.pid,
        name=definition.name,
        label=definition.label,
        value=round(value, 3),
        unit=definition.unit,
    )
