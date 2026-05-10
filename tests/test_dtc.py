from obd_ii_mcp.dtc import decode_code, parse_dtc_response


def test_parse_stored_dtcs() -> None:
    codes = parse_dtc_response(["43 01 71 03 00 00 00"], "43")
    assert [code.code for code in codes] == ["P0171", "P0300"]
    assert codes[0].description == "System too lean bank 1"


def test_parse_pending_dtcs() -> None:
    codes = parse_dtc_response(["47 01 02 00 00"], "47")
    assert codes[0].code == "P0102"


def test_parse_permanent_dtcs() -> None:
    codes = parse_dtc_response(["4A 04 20 00 00"], "4A")
    assert codes[0].code == "P0420"


def test_unknown_code_falls_back() -> None:
    decoded = decode_code("P9999")
    assert decoded.known is False
    assert decoded.description == "Unknown generic or manufacturer-specific DTC"
