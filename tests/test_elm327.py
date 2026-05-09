import pytest

from obd_ii_mcp.elm327 import clean_response, normalize_hex_lines
from obd_ii_mcp.errors import NoEcuResponseError


def test_clean_response_removes_echo_prompt_and_searching() -> None:
    assert clean_response("010C\rSEARCHING...\r41 0C 1A F8\r>", "010C") == ["41 0C 1A F8"]


def test_normalize_hex_lines_extracts_hex() -> None:
    assert normalize_hex_lines(["41 0C 1A F8"]) == ["41 0C 1A F8"]


def test_normalize_hex_lines_maps_no_data() -> None:
    with pytest.raises(NoEcuResponseError):
        normalize_hex_lines(["NO DATA"])
