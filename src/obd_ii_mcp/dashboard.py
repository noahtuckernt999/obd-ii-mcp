from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import altair as alt
import streamlit as st

from obd_ii_mcp.config import Settings, load_settings
from obd_ii_mcp.errors import ObdError
from obd_ii_mcp.models import DataSeries, LiveDataCapture, LiveValue, SampleResult, SeriesPoint
from obd_ii_mcp.pids import PID_DEFINITIONS
from obd_ii_mcp.service import ObdService
from obd_ii_mcp.sessions import write_session

DEFAULT_PIDS = ["0C", "0D", "05", "0F", "11", "42"]


@st.cache_resource
def _service(source: str, replay_file: str | None) -> ObdService:
    settings = load_settings()
    if source == "Replay file":
        settings = settings.model_copy(update={"replay_file": Path(replay_file) if replay_file else None})
    else:
        settings = settings.model_copy(update={"replay_file": None})
    return ObdService(settings)


def _pid_options() -> dict[str, str]:
    return {
        pid: f"{definition.label} ({definition.unit})"
        for pid, definition in sorted(PID_DEFINITIONS.items())
    }


def _ensure_state() -> None:
    st.session_state.setdefault("source", _default_source())
    st.session_state.setdefault("selected_replay_file", _default_replay_file())
    st.session_state.setdefault("streaming", False)
    st.session_state.setdefault("samples", [])
    st.session_state.setdefault("last_error", None)
    st.session_state.setdefault("connection_message", None)
    st.session_state.setdefault("loaded_replay_file", None)
    st.session_state.setdefault("last_stream_wall", None)
    st.session_state.setdefault("next_elapsed_seconds", 0.0)
    st.session_state.setdefault("recording", False)
    st.session_state.setdefault("recording_started_at", None)
    st.session_state.setdefault("recording_samples", [])
    st.session_state.setdefault("capture_name", "")
    st.session_state.setdefault("last_capture_file", None)


def _default_source() -> str:
    return "Replay file" if load_settings().replay_file else "Live adapter"


def _default_replay_file() -> str | None:
    replay_file = load_settings().replay_file
    if replay_file is not None:
        return str(replay_file)
    captures = _capture_files(load_settings())
    return str(captures[0]) if captures else None


def _capture_files(settings: Settings) -> list[Path]:
    if not settings.capture_dir.exists():
        return []
    return sorted(settings.capture_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _capture_label(path: str) -> str:
    capture_path = Path(path)
    try:
        capture = LiveDataCapture.model_validate_json(capture_path.read_text(encoding="utf-8"))
    except Exception:
        return capture_path.name
    duration_seconds = int((capture.sample.finished_at - capture.sample.started_at).total_seconds())
    minutes, seconds = divmod(duration_seconds, 60)
    return f"{capture_path.name} ({minutes:02d}:{seconds:02d})"


def _reset_view() -> None:
    st.session_state.streaming = False
    st.session_state.samples = []
    st.session_state.loaded_replay_file = None
    st.session_state.last_stream_wall = None
    st.session_state.next_elapsed_seconds = 0.0
    st.session_state.recording = False
    st.session_state.recording_started_at = None
    st.session_state.recording_samples = []
    st.session_state.capture_name = ""
    st.session_state.connection_message = None


def _status_badge(service: ObdService) -> None:
    status = service.status()
    if status.connected:
        st.success(
            f"Connected: {status.adapter_id or 'adapter'}"
            f" on {status.port or 'replay'}"
            f" ({status.protocol or 'protocol pending'})"
        )
    else:
        st.warning("Not connected")


def _append_values(values: list[LiveValue]) -> None:
    sampled_at = datetime.now()
    last_stream_wall = st.session_state.last_stream_wall
    if last_stream_wall is not None:
        delta_seconds = (sampled_at - last_stream_wall).total_seconds()
        st.session_state.next_elapsed_seconds += max(delta_seconds, 0)

    elapsed_seconds = round(st.session_state.next_elapsed_seconds, 3)
    st.session_state.last_stream_wall = sampled_at

    for value in values:
        sample = {
            "timestamp": sampled_at,
            "elapsed_seconds": elapsed_seconds,
            "pid": value.pid,
            "label": value.label,
            "value": value.value,
            "unit": value.unit,
        }
        st.session_state.samples.append(sample)
        if st.session_state.recording:
            st.session_state.recording_samples.append(sample)


@st.cache_data
def _capture_samples(path: str) -> list[dict[str, Any]]:
    capture = LiveDataCapture.model_validate_json(Path(path).read_text(encoding="utf-8"))
    samples = []
    started_at = capture.sample.started_at
    for series in capture.sample.series:
        for point in series.points:
            samples.append(
                {
                    "timestamp": point.timestamp,
                    "elapsed_seconds": round((point.timestamp - started_at).total_seconds(), 3),
                    "pid": series.pid,
                    "label": series.label,
                    "value": point.value,
                    "unit": series.unit,
                }
            )
    return sorted(samples, key=lambda sample: sample["timestamp"])


def _preload_replay_samples(service: ObdService) -> None:
    replay_file = service.settings.replay_file
    if replay_file is None:
        return

    replay_path = str(replay_file)
    if st.session_state.loaded_replay_file == replay_path:
        return

    try:
        service.connect()
        st.session_state.samples = _capture_samples(replay_path)
        st.session_state.loaded_replay_file = replay_path
        st.session_state.last_stream_wall = None
        st.session_state.next_elapsed_seconds = _latest_elapsed_seconds()
        st.session_state.last_error = None
    except ObdError as error:
        st.session_state.last_error = error.message
    except Exception as error:
        st.session_state.last_error = str(error)


def _trim_samples(max_points: int, selected_pids: list[str]) -> None:
    limit = max_points * max(len(selected_pids), 1)
    if len(st.session_state.samples) > limit:
        st.session_state.samples = st.session_state.samples[-limit:]


def _latest_by_pid() -> dict[str, dict[str, Any]]:
    latest = {}
    for sample in st.session_state.samples:
        latest[sample["pid"]] = sample
    return latest


def _latest_elapsed_seconds() -> float:
    if not st.session_state.samples:
        return 0.0
    return max(float(sample.get("elapsed_seconds", 0)) for sample in st.session_state.samples)


def _recording_seconds() -> int:
    started_at = st.session_state.recording_started_at
    if started_at is None:
        return 0
    return int((datetime.now() - started_at).total_seconds())


def _recording_label() -> str:
    seconds = _recording_seconds()
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _capture_prefix(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    slug = slug.strip("-")
    return f"live-data-{slug}" if slug else "live-data"


def _capture_name_from_path(path: str) -> str:
    stem = Path(path).stem
    match = re.match(r"^\d{8}-\d{6}-live-data(?:-(?P<name>.*))?$", stem)
    if not match:
        return ""
    return (match.group("name") or "").replace("-", " ")


def _rename_capture(path: str, name: str) -> str:
    current = Path(path)
    match = re.match(r"^(?P<stamp>\d{8}-\d{6})-live-data(?:-.*)?$", current.stem)
    if not match:
        raise ValueError(f"Capture filename {current.name!r} does not use the expected timestamp format")

    target = current.with_name(f"{match.group('stamp')}-{_capture_prefix(name)}{current.suffix}")
    if target == current:
        return str(current)
    if target.exists():
        raise ValueError(f"Capture file {target.name!r} already exists")

    current.rename(target)
    return str(target)


def _start_recording() -> None:
    st.session_state.streaming = True
    st.session_state.recording = True
    st.session_state.recording_started_at = datetime.now()
    st.session_state.recording_samples = []
    st.session_state.last_capture_file = None
    st.session_state.last_error = None
    st.session_state.last_stream_wall = None
    st.session_state.next_elapsed_seconds = _latest_elapsed_seconds()


def _stop_recording(service: ObdService, interval_seconds: float, capture_name: str) -> None:
    if not st.session_state.recording:
        return

    samples = st.session_state.recording_samples
    st.session_state.recording = False
    st.session_state.recording_started_at = None

    if not samples:
        st.session_state.last_error = "Recording stopped before any samples were captured."
        return

    started_at = min(sample["timestamp"] for sample in samples)
    finished_at = max(sample["timestamp"] for sample in samples)
    series = []
    for pid in sorted({sample["pid"] for sample in samples}):
        definition = PID_DEFINITIONS[pid]
        points = [
            SeriesPoint(timestamp=sample["timestamp"], value=sample["value"])
            for sample in samples
            if sample["pid"] == pid
        ]
        series.append(
            DataSeries(
                pid=definition.pid,
                name=definition.name,
                label=definition.label,
                unit=definition.unit,
                points=points,
            )
        )

    capture = LiveDataCapture(
        ok=True,
        captured_at=datetime.now(),
        status=service.status().model_dump(),
        sample=SampleResult(
            ok=True,
            started_at=started_at,
            finished_at=finished_at,
            interval_seconds=interval_seconds,
            series=series,
        ),
    )
    path = write_session(service.settings.capture_dir, _capture_prefix(capture_name), capture.model_dump())
    capture.capture_file = str(path)
    path.write_text(capture.model_dump_json(indent=2), encoding="utf-8")
    st.session_state.last_capture_file = str(path)
    st.session_state.recording_samples = []


def _render_recording_status() -> None:
    if st.session_state.recording:
        st.markdown(
            """
            <style>
            @keyframes obdPulse { 0% { opacity: .35; } 50% { opacity: 1; } 100% { opacity: .35; } }
            .recording-pill {
              color: #b00020;
              font-weight: 700;
              animation: obdPulse 1s infinite;
            }
            </style>
            <div class="recording-pill">● Recording """ + _recording_label() + """</div>
            """,
            unsafe_allow_html=True,
        )
    elif st.session_state.last_capture_file:
        st.success(f"Saved {st.session_state.last_capture_file}")


def _render_metrics(selected_pids: list[str]) -> None:
    latest = _latest_by_pid()
    columns = st.columns(min(len(selected_pids), 4) or 1)
    for index, pid in enumerate(selected_pids):
        definition = PID_DEFINITIONS[pid]
        sample = latest.get(pid)
        value = "Waiting"
        if sample is not None:
            value = f"{sample['value']} {sample['unit']}"
        columns[index % len(columns)].metric(definition.label, value)


def _render_chart(selected_pids: list[str], autoscale: bool) -> None:
    if not st.session_state.samples:
        st.info("Start streaming to see live data.")
        return

    chart_rows = [
        {
            "seconds": sample.get("elapsed_seconds", 0),
            "signal": sample["label"],
            "value": sample["value"],
        }
        for sample in st.session_state.samples
        if sample["pid"] in selected_pids and isinstance(sample["value"], int | float)
    ]
    if not chart_rows:
        st.info("No numeric samples available yet.")
        return

    y_scale = alt.Scale(zero=False) if autoscale else alt.Scale(zero=True)
    chart = (
        alt.Chart(alt.Data(values=chart_rows))
        .mark_line()
        .encode(
            x=alt.X("seconds:Q", title="seconds"),
            y=alt.Y("value:Q", title="value", scale=y_scale),
            color=alt.Color("signal:N", title="signal"),
            tooltip=[
                alt.Tooltip("seconds:Q", format=".3f"),
                alt.Tooltip("value:Q", format=".3f"),
                alt.Tooltip("signal:N"),
            ],
        )
        .properties(height=420)
    )
    st.altair_chart(chart, use_container_width=True)


def _read_once(service: ObdService, selected_pids: list[str]) -> None:
    try:
        result = service.live_data(selected_pids)
    except ObdError as error:
        st.session_state.last_error = error.message
        st.session_state.streaming = False
        return
    except Exception as error:
        st.session_state.last_error = str(error)
        st.session_state.streaming = False
        return

    st.session_state.last_error = None
    _append_values(result.values)


def app() -> None:
    st.set_page_config(page_title="OBD-II Live", layout="wide")
    _ensure_state()
    settings = load_settings()
    replay_files = [str(path) for path in _capture_files(settings)]
    if st.session_state.selected_replay_file not in replay_files and replay_files:
        st.session_state.selected_replay_file = replay_files[0]

    service = _service(st.session_state.source, st.session_state.selected_replay_file)
    _preload_replay_samples(service)
    pid_options = _pid_options()

    st.title("OBD-II Live")

    with st.sidebar:
        st.header("Data Source")
        source = st.radio(
            "Mode",
            ["Live adapter", "Replay file"],
            key="source_picker",
            index=0 if st.session_state.source == "Live adapter" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        if source != st.session_state.source:
            st.session_state.source = source
            _reset_view()
            st.cache_resource.clear()
            st.rerun()

        if st.session_state.source == "Replay file":
            if replay_files:
                selected_replay_file = st.selectbox(
                    "Capture",
                    replay_files,
                    index=replay_files.index(st.session_state.selected_replay_file),
                    format_func=_capture_label,
                )
                if selected_replay_file != st.session_state.selected_replay_file:
                    st.session_state.selected_replay_file = selected_replay_file
                    _reset_view()
                    st.cache_resource.clear()
                    st.rerun()
                rename_name = st.text_input(
                    "Rename capture",
                    value=_capture_name_from_path(st.session_state.selected_replay_file),
                    key=f"rename_{Path(st.session_state.selected_replay_file).stem}",
                    placeholder="round-block, cold-start, voltage-test",
                )
                if st.button("Rename selected capture", use_container_width=True):
                    try:
                        renamed = _rename_capture(st.session_state.selected_replay_file, rename_name)
                        st.session_state.selected_replay_file = renamed
                        _reset_view()
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.rerun()
                    except Exception as error:
                        st.session_state.last_error = str(error)
            else:
                st.warning("No capture files found.")

        st.header("Connection")
        _status_badge(service)
        if st.session_state.connection_message:
            st.caption(st.session_state.connection_message)

        connected = service.status().connected
        connect_label = "Reconnect" if connected else "Connect"
        if st.button(connect_label, use_container_width=True):
            if connected:
                status = service.status()
                st.session_state.connection_message = (
                    f"Still connected to {status.adapter_id or 'adapter'}"
                    f" on {status.port or 'unknown port'}"
                )
                st.session_state.last_error = None
            else:
                st.session_state.connection_message = "Connecting to adapter..."
                try:
                    with st.spinner("Connecting to adapter..."):
                        result = service.connect()
                    status = result.status
                    st.session_state.connection_message = (
                        f"Connected to {status.adapter_id or 'adapter'}"
                        f" on {status.port or 'unknown port'}"
                    )
                    st.session_state.last_error = None
                except ObdError as error:
                    st.session_state.connection_message = "Connection failed"
                    st.session_state.last_error = error.message
                except Exception as error:
                    st.session_state.connection_message = "Connection failed"
                    st.session_state.last_error = str(error)
            st.rerun()

        st.header("Stream")
        selected_pids = st.multiselect(
            "Signals",
            options=list(pid_options),
            default=DEFAULT_PIDS,
            format_func=pid_options.__getitem__,
        )
        interval_seconds = st.slider("Interval", 0.25, 5.0, 1.0, 0.25, format="%.2f s")
        max_points = st.slider("History", 20, 600, 120, 20, format="%d samples")
        autoscale = st.toggle("Autoscale chart", value=True)

        col_start, col_stop = st.columns(2)
        if col_start.button("Start", disabled=not selected_pids, use_container_width=True):
            st.session_state.streaming = True
            st.session_state.last_error = None
            st.session_state.last_stream_wall = None
            st.session_state.next_elapsed_seconds = _latest_elapsed_seconds()
        if col_stop.button("Stop", use_container_width=True):
            st.session_state.streaming = False

        st.header("Recording")
        _render_recording_status()
        capture_name = st.text_input(
            "Capture name",
            key="capture_name",
            placeholder="round-block, cold-start, motorway-pull",
            disabled=st.session_state.recording,
        )
        record_start, record_stop = st.columns(2)
        if record_start.button(
            "Record",
            disabled=(
                not selected_pids
                or st.session_state.recording
                or st.session_state.source == "Replay file"
            ),
            use_container_width=True,
        ):
            _start_recording()
        if record_stop.button(
            "Stop & Save",
            disabled=not st.session_state.recording,
            use_container_width=True,
        ):
            _stop_recording(service, interval_seconds, capture_name)

        if st.button("Clear", use_container_width=True):
            st.session_state.samples = []
            st.session_state.last_error = None
            st.session_state.loaded_replay_file = None
            st.session_state.last_stream_wall = None
            st.session_state.next_elapsed_seconds = 0.0
            st.session_state.last_capture_file = None
            st.session_state.capture_name = ""

    if st.session_state.last_error:
        st.error(st.session_state.last_error)

    _render_metrics(selected_pids)
    _render_chart(selected_pids, autoscale)

    if st.session_state.streaming and selected_pids:
        _read_once(service, selected_pids)
        _trim_samples(max_points, selected_pids)
        time.sleep(interval_seconds)
        st.rerun()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
