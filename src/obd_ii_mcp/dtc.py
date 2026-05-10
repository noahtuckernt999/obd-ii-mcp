from __future__ import annotations

from obd_ii_mcp.errors import MalformedResponseError
from obd_ii_mcp.models import DecodedCode, Dtc

GENERIC_DTC_DEFINITIONS: dict[str, str] = {
    "P0001": "Fuel volume regulator control circuit/open",
    "P0010": "A camshaft position actuator circuit bank 1",
    "P0100": "Mass or volume air flow circuit",
    "P0101": "Mass or volume air flow circuit range/performance",
    "P0102": "Mass or volume air flow circuit low input",
    "P0103": "Mass or volume air flow circuit high input",
    "P0113": "Intake air temperature sensor 1 circuit high",
    "P0115": "Engine coolant temperature sensor 1 circuit",
    "P0128": "Coolant thermostat below regulating temperature",
    "P0130": "O2 sensor circuit bank 1 sensor 1",
    "P0171": "System too lean bank 1",
    "P0172": "System too rich bank 1",
    "P0201": "Injector circuit/open cylinder 1",
    "P0300": "Random/multiple cylinder misfire detected",
    "P0301": "Cylinder 1 misfire detected",
    "P0302": "Cylinder 2 misfire detected",
    "P0303": "Cylinder 3 misfire detected",
    "P0304": "Cylinder 4 misfire detected",
    "P0325": "Knock sensor 1 circuit bank 1",
    "P0401": "Exhaust gas recirculation flow insufficient detected",
    "P0420": "Catalyst system efficiency below threshold bank 1",
    "P0442": "Evaporative emission system leak detected small leak",
    "P0455": "Evaporative emission system leak detected gross leak",
    "P0500": "Vehicle speed sensor",
    "P0562": "System voltage low",
    "P0563": "System voltage high",
}

SYSTEMS = {
    "P": "Powertrain",
    "C": "Chassis",
    "B": "Body",
    "U": "Network",
}


def decode_code(code: str) -> DecodedCode:
    normalized = code.strip().upper()
    description = GENERIC_DTC_DEFINITIONS.get(normalized, "Unknown generic or manufacturer-specific DTC")
    return DecodedCode(
        ok=True,
        code=normalized,
        description=description,
        known=normalized in GENERIC_DTC_DEFINITIONS,
        system=SYSTEMS.get(normalized[:1], "Unknown"),
    )


def _dtc_from_pair(first: int, second: int) -> str:
    systems = ["P", "C", "B", "U"]
    system = systems[(first & 0xC0) >> 6]
    digit_1 = (first & 0x30) >> 4
    digit_2 = first & 0x0F
    return f"{system}{digit_1}{digit_2:X}{second:02X}"


def parse_dtc_response(hex_lines: list[str], response_mode: str) -> list[Dtc]:
    bytes_: list[int] = []
    response_value = int(response_mode, 16)
    for line in hex_lines:
        values = [int(token, 16) for token in line.split()]
        if response_value in values:
            start = values.index(response_value)
            bytes_.extend(values[start + 1 :])

    if not bytes_:
        raise MalformedResponseError(f"No {response_mode} response bytes found")

    codes: list[Dtc] = []
    for index in range(0, len(bytes_) - 1, 2):
        first, second = bytes_[index], bytes_[index + 1]
        if first == 0 and second == 0:
            continue
        code = _dtc_from_pair(first, second)
        decoded = decode_code(code)
        codes.append(Dtc(code=code, description=decoded.description, raw=f"{first:02X}{second:02X}"))
    return codes
