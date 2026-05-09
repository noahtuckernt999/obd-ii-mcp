from pathlib import Path

from obd_ii_mcp.config import Settings
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


def test_probe_skips_bad_ports_and_falls_back_baud(tmp_path: Path) -> None:
    service = make_service(tmp_path, {("COM9", 9600): BASE_INIT})
    result = service.connect()
    assert result.ok is True
    assert result.status.port == "COM9"
    assert result.status.baud_rate == 9600


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
