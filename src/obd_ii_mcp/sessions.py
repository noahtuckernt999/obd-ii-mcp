from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def write_session(session_dir: Path, prefix: str, payload: dict[str, Any]) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = session_dir / f"{stamp}-{prefix}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
