# Agent Notes

## Project Context

This repo builds a read-only MCP server and Streamlit dashboard for ELM327-compatible OBD-II adapters.

Core flow:

- MCP tools expose safe diagnostic actions.
- `ObdService` owns connection, live reads, sampling, capture, replay, and diagnostic workflows.
- `elm327.py` owns the ELM327 adapter command layer.
- `transport.py` owns serial port I/O.
- `pids.py` and `dtc.py` own decoding/parsing.
- `dashboard.py` provides live/replay visualisation and capture management.

## Windows And Tooling Gotchas

- GitHub CLI auth may work in the user's terminal while sandboxed agent commands still report an invalid token.
- On this machine, running `gh` with elevated permissions allowed access to the Windows keyring and fixed PR creation.
- The WinGet `uv.exe` shim may fail from the sandbox. Prefer the repo venv directly when needed:
  `.\.venv\Scripts\python.exe ...`
- Pytest may need a workspace-local temp path:
  `.\.venv\Scripts\python.exe -m pytest --basetemp .pytest-cache-local\tmp -p no:cacheprovider`

## OBD And Streamlit Gotchas

- Windows serial ports are exclusive. If Streamlit cannot connect to the adapter, another MCP, Streamlit, or Python process may be holding `COM7`.
- Replay mode is controlled by `OBD_MCP_REPLAY_FILE`; live mode should clear it.
- For live car sessions on this setup, pinning `OBD_MCP_SERIAL_PORTS=COM7` avoids slow or confusing port probing.
- Streamlit reruns the script on interaction; the dashboard keeps live samples in `st.session_state`.

## Useful Commands

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest-cache-local\tmp -p no:cacheprovider
```

Run the dashboard:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m streamlit run src\obd_ii_mcp\dashboard.py
```

Run dashboard against replay:

```powershell
$env:PYTHONPATH = "src"
$env:OBD_MCP_REPLAY_FILE = ".obd-mcp\captures\<capture>.json"
.\.venv\Scripts\python.exe -m streamlit run src\obd_ii_mcp\dashboard.py
```
