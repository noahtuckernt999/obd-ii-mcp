from pathlib import Path

from obd_ii_mcp.config import Settings
from obd_ii_mcp.errors import UnsupportedDataIdentifierError
from obd_ii_mcp.models import PortCandidate
from obd_ii_mcp.service import ObdService
from obd_ii_mcp.transport import FakeTransport


def make_service(tmp_path: Path, responses_by_port: dict[tuple[str, int], dict[str, str]]) -> ObdService:
    def factory(port: str, baud: int, _timeout: float) -> FakeTransport:
        return FakeTransport(port=port, baud_rate=baud, responses=responses_by_port.get((port, baud), {}))

    return ObdService(
        Settings(session_dir=tmp_path),
        transport_factory=factory,
        port_lister=lambda: [
            PortCandidate(device="COM3", description="Intel(R) Active Management Technology - SOL"),
            PortCandidate(device="COM4", description="Standard Serial over Bluetooth link"),
            PortCandidate(device="COM9", description="Standard Serial over Bluetooth link"),
        ],
    )


BASE_INIT = {
    "ATZ": "ELM327 v1.5\r>",
    "ATE0": "OK\r>",
    "ATL0": "OK\r>",
    "ATS0": "OK\r>",
    "ATH0": "OK\r>",
    "ATI": "ELM327 v1.5\r>",
    "ATSP0": "OK\r>",
    "ATDP": "AUTO, ISO 15765-4 CAN\r>",
}


def support_response(start: int, pids: list[int]) -> str:
    payload = [0, 0, 0, 0]
    for pid in pids:
        bit_index = pid - start - 1
        payload[bit_index // 8] |= 1 << (7 - (bit_index % 8))
    return f"41 {start:02X} {' '.join(f'{value:02X}' for value in payload)}\r>"


def test_probe_skips_bad_ports_and_falls_back_baud(tmp_path: Path) -> None:
    service = make_service(tmp_path, {("COM9", 9600): BASE_INIT})
    result = service.connect()
    assert result.ok is True
    assert result.status.port == "COM9"
    assert result.status.baud_rate == 9600


def test_disconnect_closes_transport_and_clears_status(tmp_path: Path) -> None:
    service = make_service(tmp_path, {("COM4", 38400): BASE_INIT})
    service.connect()
    transport = service.transport
    assert transport is not None

    result = service.disconnect()

    assert result.ok is True
    assert result.released is True
    assert result.status.connected is False
    assert service.status().connected is False
    assert transport.opened is False
    assert service.transport is None
    assert service.protocol is None


def test_read_codes_with_fake_transport(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "03": "43 01 71 00 00\r>",
        "07": "NO DATA\r>",
        "0A": "NO DATA\r>",
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})
    codes = service.read_codes()
    assert [code.code for code in codes.stored] == ["P0171"]
    assert codes.pending == []
    assert codes.permanent == []


def test_fault_snapshot_writes_session(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "03": "43 01 71 00 00\r>",
        "07": "NO DATA\r>",
        "0A": "NO DATA\r>",
        "010C": "41 0C 1A F8\r>",
        "010D": "41 0D 28\r>",
        "0105": "41 05 7B\r>",
        "010F": "41 0F 50\r>",
        "0111": "41 11 80\r>",
        "0142": "41 42 2E E0\r>",
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})
    snapshot = service.fault_snapshot()
    assert snapshot.session_file is not None
    assert Path(snapshot.session_file).exists()
    assert snapshot.codes.stored[0].code == "P0171"


def test_record_live_data_writes_replayable_capture(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "0142": "41 42 30 97\r>",
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})
    service.settings.capture_dir = tmp_path / "captures"
    capture = service.record_live_data(["42"], duration_seconds=0, interval_seconds=1)

    assert capture.capture_file is not None
    assert Path(capture.capture_file).exists()
    assert capture.sample.series[0].points[0].value == 12.439

    replay_service = ObdService(Settings(replay_file=Path(capture.capture_file), session_dir=tmp_path))
    result = replay_service.live_data(["42"])

    assert replay_service.status().protocol == "replay"
    assert result.values[0].pid == "42"
    assert result.values[0].value == 12.439


def test_discover_pids_returns_decoded_and_undecoded_supported_pids(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "0100": support_response(0x00, [0x04, 0x05, 0x0C, 0x0D, 0x12, 0x20]),
        "0120": support_response(0x20, [0x40]),
        "0140": support_response(0x40, [0x42, 0x46]),
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})

    result = service.discover_pids()

    decoded = {pid.pid for pid in result.decoded}
    undecoded = {pid.pid for pid in result.undecoded}
    assert {"04", "05", "0C", "0D", "20", "40", "42", "46"} <= decoded
    assert {"12"} <= undecoded
    assert any(pid.pid == "42" and pid.group == "Electrical" for pid in result.decoded)


def test_probe_enhanced_protocols_reads_uds_vin_when_can_is_active(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "ATDPN": "A6\r>",
        "ATCS": "OK\r>",
        "ATAL": "OK\r>",
        "ATH1": "OK\r>",
        "ATCAF1": "OK\r>",
        "ATCFC1": "OK\r>",
        "ATSH7E0": "OK\r>",
        "ATCRA7E8": "OK\r>",
        "22F190": "7E8 10 14 62 F1 90 57 41\r7E8 21 55 5A 5A 5A 5A 5A\r>",
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})

    result = service.probe_enhanced_protocols()

    assert result.uds_possible is True
    assert result.kwp_possible is False
    assert any(step.name == "uds_vin_read" and step.value == "TESTVIN1" for step in result.steps)


def test_read_data_identifier_reads_allowlisted_vin(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "ATAL": "OK\r>",
        "ATH1": "OK\r>",
        "ATCAF1": "OK\r>",
        "ATCFC1": "OK\r>",
        "ATSH7E0": "OK\r>",
        "ATCRA7E8": "OK\r>",
        "22F190": "7E8 10 14 62 F1 90 57 41\r7E8 21 55 5A 5A 5A 5A 5A\r>",
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})

    result = service.read_data_identifier("F190")

    assert result.ok is True
    assert result.request == "22 F1 90"
    assert result.value == "TESTVIN1"


def test_read_data_identifier_reads_allowlisted_ecu_identity(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "ATAL": "OK\r>",
        "ATH1": "OK\r>",
        "ATCAF1": "OK\r>",
        "ATCFC1": "OK\r>",
        "ATSH7E0": "OK\r>",
        "ATCRA7E8": "OK\r>",
        "22F188": "7E8 10 0D 62 F1 88 30 34\r7E8 21 45 39 30 36 30 32 36\r7E8 22 44\r>",
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})

    result = service.read_data_identifier("F188")

    assert result.ok is True
    assert result.name == "ECU software number"
    assert result.request == "22 F1 88"
    assert result.value == "04E906026D"


def test_read_data_identifier_reads_compact_can_frame_vin(tmp_path: Path) -> None:
    responses = BASE_INIT | {
        "ATAL": "OK\r>",
        "ATH1": "OK\r>",
        "ATCAF1": "OK\r>",
        "ATCFC1": "OK\r>",
        "ATSH7E0": "OK\r>",
        "ATCRA7E8": "OK\r>",
        "22F190": "7E8101462F190574155\r7E8215A5A5A3856334A\r7E82241303138383931\r>",
    }
    service = make_service(tmp_path, {("COM4", 38400): responses})

    result = service.read_data_identifier("F190")

    assert result.ok is True
    assert result.value == "TESTVIN1234567890"
    assert result.raw_payload == [
        "57",
        "41",
        "55",
        "5A",
        "5A",
        "5A",
        "38",
        "56",
        "33",
        "4A",
        "41",
        "30",
        "31",
        "38",
        "38",
        "39",
        "31",
    ]


def test_read_data_identifier_rejects_unknown_did(tmp_path: Path) -> None:
    service = make_service(tmp_path, {("COM4", 38400): BASE_INIT})

    result = service.read_data_identifier

    try:
        result("F1FF")
    except UnsupportedDataIdentifierError as error:
        assert "allow-list" in str(error)
    else:
        raise AssertionError("Expected unsupported DID to raise")
