from __future__ import annotations

import argparse
import traceback
from datetime import datetime
from pathlib import Path

from obd_ii_mcp.config import load_settings
from obd_ii_mcp.service import ObdService


def _log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now().isoformat()} {message}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=300)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--log", type=Path, default=Path(".obd-mcp/live-drive-recording.log"))
    parser.add_argument("--pids", nargs="+", default=["0C", "0D", "05", "0F", "11", "42"])
    args = parser.parse_args()

    args.log.write_text("", encoding="utf-8")
    _log(args.log, f"starting duration={args.duration}s interval={args.interval}s pids={args.pids}")

    try:
        service = ObdService(load_settings())
        result = service.connect()
        _log(args.log, f"connected {result.status.model_dump()}")

        first = service.live_data(args.pids)
        _log(args.log, f"RECORDING first_sample {[value.model_dump() for value in first.values]}")

        capture = service.record_live_data(
            args.pids,
            duration_seconds=args.duration,
            interval_seconds=args.interval,
        )
        _log(args.log, f"finished {capture.capture_file}")
    except Exception as error:
        _log(args.log, f"ERROR {error}")
        _log(args.log, traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
