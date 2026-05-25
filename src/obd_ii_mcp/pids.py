from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from obd_ii_mcp.errors import MalformedResponseError, UnsupportedPidError
from obd_ii_mcp.models import LiveValue

DecodedValue = float | str
Decoder = Callable[[list[int]], DecodedValue]


@dataclass(frozen=True)
class PidDefinition:
    pid: str
    name: str
    label: str
    unit: str
    byte_count: int
    decoder: Decoder


def _one(transform: Callable[[int], DecodedValue]) -> Decoder:
    return lambda data: transform(data[0])


def _two(transform: Callable[[int, int], DecodedValue]) -> Decoder:
    return lambda data: transform(data[0], data[1])


def _uint16(a: int, b: int) -> int:
    return (a * 256) + b


def _percent(a: int) -> float:
    return a * 100 / 255


def _trim(a: int) -> float:
    return (a - 128) * 100 / 128


def _supported_range(start: int) -> Decoder:
    def decode(data: list[int]) -> str:
        supported = []
        for bit_index in range(32):
            byte = data[bit_index // 8]
            mask = 1 << (7 - (bit_index % 8))
            if byte & mask:
                supported.append(f"{start + bit_index + 1:02X}")
        return ", ".join(supported) if supported else "None"

    return decode


def _monitor_status(data: list[int]) -> str:
    mil = "on" if data[0] & 0x80 else "off"
    dtc_count = data[0] & 0x7F
    return f"MIL {mil}; {dtc_count} stored DTCs"


FUEL_SYSTEM_STATUS = {
    0x01: "Open loop due to insufficient engine temperature",
    0x02: "Closed loop using oxygen sensor feedback",
    0x04: "Open loop due to engine load or deceleration",
    0x08: "Open loop due to system failure",
    0x10: "Closed loop with oxygen sensor fault",
}


def _fuel_system_status(data: list[int]) -> str:
    values = []
    for index, value in enumerate(data[:2], start=1):
        label = FUEL_SYSTEM_STATUS.get(value, f"Status 0x{value:02X}") if value else "Not used"
        values.append(f"system {index}: {label}")
    return "; ".join(values)


def _o2_sensors_present(data: list[int]) -> str:
    sensors = [f"O2S{index + 1}" for index in range(8) if data[0] & (1 << index)]
    return ", ".join(sensors) if sensors else "None"


OBD_STANDARDS = {
    1: "OBD-II as defined by CARB",
    2: "OBD as defined by EPA",
    3: "OBD and OBD-II",
    4: "OBD-I",
    5: "Not OBD compliant",
    6: "EOBD",
    7: "EOBD and OBD-II",
    8: "EOBD and OBD",
    9: "EOBD, OBD and OBD-II",
    10: "JOBD",
    11: "JOBD and OBD-II",
    12: "JOBD and EOBD",
    13: "JOBD, EOBD and OBD-II",
    17: "Engine manufacturer diagnostics",
    18: "Engine manufacturer diagnostics enhanced",
    19: "Heavy duty OBD",
    20: "Heavy duty OBD",
    21: "World wide harmonized OBD",
    23: "Heavy duty EOBD stage I",
    24: "Heavy duty EOBD stage I and N",
    25: "Heavy duty EOBD stage II",
    26: "Heavy duty EOBD stage II and N",
    28: "Brazil OBD phase 1",
    29: "Brazil OBD phase 2",
    30: "Korean OBD",
    31: "India OBD I",
    32: "India OBD II",
    33: "Heavy duty Euro OBD stage VI",
}


FUEL_TYPES = {
    1: "Gasoline",
    2: "Methanol",
    3: "Ethanol",
    4: "Diesel",
    5: "LPG",
    6: "CNG",
    7: "Propane",
    8: "Electric",
    9: "Bifuel gasoline",
    10: "Bifuel methanol",
    11: "Bifuel ethanol",
    12: "Bifuel LPG",
    13: "Bifuel CNG",
    14: "Bifuel propane",
    15: "Bifuel electricity",
    16: "Bifuel electric and combustion",
    17: "Hybrid gasoline",
    18: "Hybrid ethanol",
    19: "Hybrid diesel",
    20: "Hybrid electric",
    21: "Hybrid mixed fuel",
    22: "Hybrid regenerative",
    23: "Bifuel diesel",
}


def _monitor_this_drive_cycle(data: list[int]) -> str:
    return f"raw monitor bitmask {' '.join(f'{value:02X}' for value in data)}"


def _max_values_4f(data: list[int]) -> str:
    return (
        f"equivalence ratio {data[0] / 255:.3f}; "
        f"O2 voltage {data[1] / 200:.3f} V; "
        f"O2 current {data[2]:.0f} mA; "
        f"intake pressure {data[3] * 10:.0f} kPa"
    )


def _max_values_50(data: list[int]) -> str:
    return (
        f"MAF {_uint16(data[0], data[1]) * 10:.0f} g/s; "
        f"air flow from MAP {data[2] * 10:.0f} g/s; "
        f"absolute pressure {data[3] * 10:.0f} kPa"
    )


def _dual_trim(data: list[int]) -> str:
    return f"bank 1 {_trim(data[0]):.1f}%; bank 3 {_trim(data[1]):.1f}%"


def _raw_bytes(data: list[int]) -> str:
    return " ".join(f"{value:02X}" for value in data)


PID_DEFINITIONS: dict[str, PidDefinition] = {
    "01": PidDefinition("01", "monitor_status", "Monitor status since DTCs cleared", "", 4, _monitor_status),
    "03": PidDefinition("03", "fuel_system_status", "Fuel system status", "", 2, _fuel_system_status),
    "04": PidDefinition("04", "calculated_engine_load", "Calculated engine load", "%", 1, _one(_percent)),
    "05": PidDefinition("05", "coolant_temp", "Engine coolant temperature", "degC", 1, _one(lambda a: a - 40)),
    "06": PidDefinition("06", "short_term_fuel_trim_b1", "Short term fuel trim bank 1", "%", 1, _one(_trim)),
    "07": PidDefinition("07", "long_term_fuel_trim_b1", "Long term fuel trim bank 1", "%", 1, _one(_trim)),
    "0B": PidDefinition("0B", "intake_manifold_pressure", "Intake manifold pressure", "kPa", 1, _one(float)),
    "0C": PidDefinition("0C", "rpm", "Engine RPM", "rpm", 2, _two(lambda a, b: _uint16(a, b) / 4)),
    "0D": PidDefinition("0D", "vehicle_speed", "Vehicle speed", "km/h", 1, _one(float)),
    "0E": PidDefinition("0E", "timing_advance", "Timing advance", "degrees", 1, _one(lambda a: (a / 2) - 64)),
    "0F": PidDefinition("0F", "intake_air_temp", "Intake air temperature", "degC", 1, _one(lambda a: a - 40)),
    "11": PidDefinition("11", "throttle_position", "Throttle position", "%", 1, _one(_percent)),
    "13": PidDefinition("13", "oxygen_sensors_present", "Oxygen sensors present", "", 1, _o2_sensors_present),
    "14": PidDefinition("14", "oxygen_sensor_1_voltage", "O2 sensor 1 voltage", "V", 2, _two(lambda a, _b: a / 200)),
    "15": PidDefinition("15", "oxygen_sensor_2_voltage", "O2 sensor 2 voltage", "V", 2, _two(lambda a, _b: a / 200)),
    "1C": PidDefinition("1C", "obd_standard", "OBD standards this vehicle conforms to", "", 1, _one(lambda a: OBD_STANDARDS.get(a, f"Standard 0x{a:02X}"))),
    "1F": PidDefinition("1F", "run_time_since_engine_start", "Run time since engine start", "s", 2, _two(_uint16)),
    "20": PidDefinition("20", "supported_pids_21_40", "Supported PIDs 21-40", "", 4, _supported_range(0x20)),
    "21": PidDefinition("21", "distance_with_mil_on", "Distance traveled with MIL on", "km", 2, _two(_uint16)),
    "23": PidDefinition("23", "fuel_rail_gauge_pressure", "Fuel rail gauge pressure", "kPa", 2, _two(lambda a, b: _uint16(a, b) * 10)),
    "2E": PidDefinition("2E", "commanded_evaporative_purge", "Commanded evaporative purge", "%", 1, _one(_percent)),
    "2F": PidDefinition("2F", "fuel_tank_level", "Fuel tank level", "%", 1, _one(_percent)),
    "30": PidDefinition("30", "warmups_since_codes_cleared", "Warm-ups since codes cleared", "count", 1, _one(float)),
    "31": PidDefinition("31", "distance_since_codes_cleared", "Distance traveled since codes cleared", "km", 2, _two(_uint16)),
    "33": PidDefinition("33", "absolute_barometric_pressure", "Absolute barometric pressure", "kPa", 1, _one(float)),
    "3C": PidDefinition("3C", "catalyst_temp_b1s1", "Catalyst temperature bank 1 sensor 1", "degC", 2, _two(lambda a, b: (_uint16(a, b) / 10) - 40)),
    "40": PidDefinition("40", "supported_pids_41_60", "Supported PIDs 41-60", "", 4, _supported_range(0x40)),
    "41": PidDefinition("41", "monitor_status_this_drive_cycle", "Monitor status this drive cycle", "", 4, _monitor_this_drive_cycle),
    "42": PidDefinition("42", "control_module_voltage", "Control module voltage", "V", 2, _two(lambda a, b: _uint16(a, b) / 1000)),
    "43": PidDefinition("43", "absolute_load", "Absolute load value", "%", 2, _two(lambda a, b: _uint16(a, b) * 100 / 255)),
    "44": PidDefinition("44", "commanded_equivalence_ratio", "Commanded air-fuel equivalence ratio", "ratio", 2, _two(lambda a, b: _uint16(a, b) / 32768)),
    "45": PidDefinition("45", "relative_throttle_position", "Relative throttle position", "%", 1, _one(_percent)),
    "46": PidDefinition("46", "ambient_air_temp", "Ambient air temperature", "degC", 1, _one(lambda a: a - 40)),
    "47": PidDefinition("47", "absolute_throttle_position_b", "Absolute throttle position B", "%", 1, _one(_percent)),
    "48": PidDefinition("48", "absolute_throttle_position_c", "Absolute throttle position C", "%", 1, _one(_percent)),
    "49": PidDefinition("49", "accelerator_pedal_position_d", "Accelerator pedal position D", "%", 1, _one(_percent)),
    "4A": PidDefinition("4A", "accelerator_pedal_position_e", "Accelerator pedal position E", "%", 1, _one(_percent)),
    "4C": PidDefinition("4C", "commanded_throttle_actuator", "Commanded throttle actuator", "%", 1, _one(_percent)),
    "4F": PidDefinition("4F", "maximum_equivalence_o2_pressure", "Maximum equivalence ratio, O2 voltage/current, and intake pressure", "", 4, _max_values_4f),
    "50": PidDefinition("50", "maximum_air_flow", "Maximum air flow rates", "", 4, _max_values_50),
    "51": PidDefinition("51", "fuel_type", "Fuel type", "", 1, _one(lambda a: FUEL_TYPES.get(a, f"Fuel type 0x{a:02X}"))),
    "56": PidDefinition("56", "long_term_secondary_o2_trim_b1_b3", "Long term secondary O2 trim bank 1 and bank 3", "", 2, _dual_trim),
    "60": PidDefinition("60", "supported_pids_61_80", "Supported PIDs 61-80", "", 4, _supported_range(0x60)),
    "70": PidDefinition("70", "pid_70_raw", "PID 70 raw value", "", 4, _raw_bytes),
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
    "timing_advance": "0E",
    "short_term_fuel_trim_b1": "06",
    "stft_b1": "06",
    "long_term_fuel_trim_b1": "07",
    "ltft_b1": "07",
    "o2s1": "14",
    "o2s2": "15",
    "fuel_level": "2F",
    "baro": "33",
    "ambient_air_temp": "46",
    "fuel_type": "51",
    "voltage": "42",
    "control_module_voltage": "42",
}

PID_GROUPS = {
    "01": "Status",
    "03": "Air and fuel",
    "04": "Engine",
    "05": "Temperature",
    "06": "Fuel trim",
    "07": "Fuel trim",
    "0B": "Air and fuel",
    "0C": "Engine",
    "0D": "Vehicle",
    "0E": "Engine",
    "0F": "Temperature",
    "11": "Engine",
    "13": "Emissions",
    "14": "Emissions",
    "15": "Emissions",
    "1C": "Status",
    "1F": "Engine",
    "20": "Support",
    "21": "Vehicle",
    "23": "Air and fuel",
    "2E": "Emissions",
    "2F": "Fuel",
    "30": "Status",
    "31": "Vehicle",
    "33": "Air and fuel",
    "3C": "Emissions",
    "40": "Support",
    "41": "Status",
    "42": "Electrical",
    "43": "Engine",
    "44": "Air and fuel",
    "45": "Engine",
    "46": "Temperature",
    "47": "Engine",
    "48": "Engine",
    "49": "Engine",
    "4A": "Engine",
    "4C": "Engine",
    "4F": "Limits",
    "50": "Limits",
    "51": "Fuel",
    "56": "Fuel trim",
    "60": "Support",
    "70": "Other",
}

STANDARD_PID_LABELS = {
    "01": "Monitor status since DTCs cleared",
    "02": "Freeze DTC",
    "03": "Fuel system status",
    "04": "Calculated engine load",
    "05": "Engine coolant temperature",
    "06": "Short term fuel trim bank 1",
    "07": "Long term fuel trim bank 1",
    "08": "Short term fuel trim bank 2",
    "09": "Long term fuel trim bank 2",
    "0A": "Fuel pressure",
    "0B": "Intake manifold pressure",
    "0C": "Engine RPM",
    "0D": "Vehicle speed",
    "0E": "Timing advance",
    "0F": "Intake air temperature",
    "10": "MAF air flow rate",
    "11": "Throttle position",
    "12": "Commanded secondary air status",
    "13": "Oxygen sensors present",
    "14": "O2 sensor 1 voltage",
    "15": "O2 sensor 2 voltage",
    "16": "O2 sensor 3 voltage",
    "17": "O2 sensor 4 voltage",
    "18": "O2 sensor 5 voltage",
    "19": "O2 sensor 6 voltage",
    "1A": "O2 sensor 7 voltage",
    "1B": "O2 sensor 8 voltage",
    "1C": "OBD standards this vehicle conforms to",
    "1D": "Oxygen sensors present",
    "1E": "Auxiliary input status",
    "1F": "Run time since engine start",
    "21": "Distance traveled with MIL on",
    "22": "Fuel rail pressure",
    "23": "Fuel rail gauge pressure",
    "2C": "Commanded EGR",
    "2D": "EGR error",
    "2E": "Commanded evaporative purge",
    "2F": "Fuel tank level",
    "30": "Warm-ups since codes cleared",
    "31": "Distance traveled since codes cleared",
    "33": "Absolute barometric pressure",
    "3C": "Catalyst temperature bank 1 sensor 1",
    "3D": "Catalyst temperature bank 2 sensor 1",
    "3E": "Catalyst temperature bank 1 sensor 2",
    "3F": "Catalyst temperature bank 2 sensor 2",
    "42": "Control module voltage",
    "43": "Absolute load value",
    "44": "Commanded air-fuel equivalence ratio",
    "45": "Relative throttle position",
    "46": "Ambient air temperature",
    "47": "Absolute throttle position B",
    "48": "Absolute throttle position C",
    "49": "Accelerator pedal position D",
    "4A": "Accelerator pedal position E",
    "4B": "Accelerator pedal position F",
    "4C": "Commanded throttle actuator",
    "4D": "Time run with MIL on",
    "4E": "Time since trouble codes cleared",
    "51": "Fuel type",
    "52": "Ethanol fuel percentage",
    "5C": "Engine oil temperature",
}


def pid_group(pid: str) -> str:
    return PID_GROUPS.get(normalize_pid(pid) if pid.upper() in PID_DEFINITIONS else pid.upper(), "Other")


def standard_pid_label(pid: str) -> str:
    normalized = pid.upper().replace("0X", "")
    definition = PID_DEFINITIONS.get(normalized)
    if definition is not None:
        return definition.label
    return STANDARD_PID_LABELS.get(normalized, f"PID {normalized}")


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
    if isinstance(value, float):
        value = round(value, 3)
    return LiveValue(
        pid=definition.pid,
        name=definition.name,
        label=definition.label,
        value=value,
        unit=definition.unit,
    )
