from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import streamlit as st

from obd_ii_mcp.config import load_settings
from obd_ii_mcp.errors import ObdError
from obd_ii_mcp.models import LiveValue
from obd_ii_mcp.pids import PID_DEFINITIONS
from obd_ii_mcp.service import ObdService

DEFAULT_PIDS = ["0C", "0D", "05", "0F", "11", "42"]


@st.cache_resource
def _service() -> ObdService:
    return ObdService(load_settings())


def _pid_options() -> dict[str, str]:
    return {
        pid: f"{definition.label} ({definition.unit})"
        for pid, definition in sorted(PID_DEFINITIONS.items())
    }


def _ensure_state() -> None:
    st.session_state.setdefault("streaming", False)
    st.session_state.setdefault("samples", [])
    st.session_state.setdefault("last_error", None)


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
    for value in values:
        st.session_state.samples.append(
            {
                "timestamp": sampled_at,
                "pid": value.pid,
                "label": value.label,
                "value": value.value,
                "unit": value.unit,
            }
        )


def _trim_samples(max_points: int, selected_pids: list[str]) -> None:
    limit = max_points * max(len(selected_pids), 1)
    if len(st.session_state.samples) > limit:
        st.session_state.samples = st.session_state.samples[-limit:]


def _latest_by_pid() -> dict[str, dict[str, Any]]:
    latest = {}
    for sample in st.session_state.samples:
        latest[sample["pid"]] = sample
    return latest


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


def _render_chart() -> None:
    if not st.session_state.samples:
        st.info("Start streaming to see live data.")
        return

    chart_rows = [
        {
            "timestamp": sample["timestamp"],
            "signal": sample["label"],
            "value": sample["value"],
        }
        for sample in st.session_state.samples
        if isinstance(sample["value"], int | float)
    ]
    if not chart_rows:
        st.info("No numeric samples available yet.")
        return

    st.line_chart(chart_rows, x="timestamp", y="value", color="signal", height=420)


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
    service = _service()
    pid_options = _pid_options()

    st.title("OBD-II Live")

    with st.sidebar:
        st.header("Connection")
        _status_badge(service)
        if st.button("Connect", use_container_width=True):
            try:
                service.connect()
                st.session_state.last_error = None
            except ObdError as error:
                st.session_state.last_error = error.message
            except Exception as error:
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

        col_start, col_stop = st.columns(2)
        if col_start.button("Start", disabled=not selected_pids, use_container_width=True):
            st.session_state.streaming = True
            st.session_state.last_error = None
        if col_stop.button("Stop", use_container_width=True):
            st.session_state.streaming = False

        if st.button("Clear", use_container_width=True):
            st.session_state.samples = []
            st.session_state.last_error = None

    if st.session_state.last_error:
        st.error(st.session_state.last_error)

    _render_metrics(selected_pids)
    _render_chart()

    if st.session_state.streaming and selected_pids:
        _read_once(service, selected_pids)
        _trim_samples(max_points, selected_pids)
        time.sleep(interval_seconds)
        st.rerun()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
