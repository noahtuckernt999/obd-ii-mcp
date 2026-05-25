# obd-ii-mcp

A read-only MCP server and Streamlit dashboard for ELM327-compatible OBD-II adapters.

The project lets Claude, Codex, or any MCP-capable client safely talk to a car through a local server. The server owns the low-level ELM327 adapter session, exposes conservative diagnostic tools, and returns structured data that an AI assistant can reason over without needing raw vehicle-bus access.

The Streamlit dashboard provides a human-facing view for live data, replay files, PID discovery, charting, and capture management.

## What It Does

- Connects to a paired Bluetooth OBD-II adapter over a Windows COM port.
- Detects and initialises an ELM327-style adapter.
- Reads live Mode 01 PID data such as RPM, speed, temperatures, load, fuel trim, throttle, O2 values, voltage, fuel level, barometric pressure, and other discovered signals.
- Discovers which Mode 01 PIDs the vehicle reports as supported.
- Separates discovered PIDs into decoded and not-yet-decoded signals.
- Reads stored, pending, and permanent diagnostic trouble codes.
- Decodes common generic OBD-II fault codes.
- Captures graph-ready time-series samples.
- Records live sessions to replayable JSON files.
- Replays captures without needing the car or adapter connected.
- Releases the serial adapter explicitly with `obd_disconnect` or the dashboard **Disconnect** button.

Clearing codes and other write/service operations are intentionally not implemented.

## MCP Tool Surface

The server exposes a conservative read-only tool surface:

| Tool | Purpose |
| --- | --- |
| `obd_connect` | Connect to a configured Bluetooth adapter and initialise the OBD session. |
| `obd_disconnect` | Close the active adapter or replay session and release the serial port. |
| `obd_status` | Report adapter connection, vehicle protocol, VIN availability, and session health. |
| `obd_read_codes` | Read stored, pending, and permanent DTCs. |
| `obd_decode_code` | Explain a DTC using built-in generic definitions and any available manufacturer notes. |
| `obd_live_data` | Read one or more supported PIDs once. |
| `obd_discover_pids` | Discover which Mode 01 PIDs the vehicle reports as supported. |
| `obd_sample_data` | Sample selected PIDs over time and return graph-ready series data. |
| `obd_record_live_data` | Record selected live PIDs to a replayable local capture file. |
| `obd_probe_enhanced_protocols` | Read-only probe for whether the current ELM327 session can carry UDS/KWP-style identity requests. |
| `obd_read_data_identifier` | Read an allow-listed UDS service `22` identity data identifier on engine ECU header `7E0`. |
| `obd_fault_snapshot` | Pull codes plus relevant live data in one diagnostic bundle. |

Write/service tools such as clearing codes are deliberately out of scope.

## Safety Boundaries

This project defaults to read-only behaviour. Anything that changes vehicle state must be gated behind configuration and require an explicit tool call. The server does not expose arbitrary raw CAN writes as an MCP tool.

Safety rules:

- Read-only mode is the default.
- Clearing codes and other write/service actions are not implemented in v1.
- Raw adapter commands are not exposed to MCP clients by default.
- Tool responses should make uncertainty clear rather than over-diagnosing.
- The server should never claim that a fault code alone proves a component has failed.

## Architecture

```text
MCP client                  Streamlit dashboard
    |                               |
    v                               v
MCP server                    ObdService
    |                               |
    +-----------> ObdService <------+
                       |
                       v
                ELM327 protocol
                       |
                       v
                Serial transport
                       |
                       v
             Bluetooth COM port / replay file
                       |
                       v
              ELM327 adapter -> vehicle ECU
```

Important modules:

- `server`: MCP server bootstrap and tool registration.
- `service`: connection lifecycle, live reads, sampling, capture, replay, PID discovery, and diagnostic workflows.
- `elm327`: ELM327 command/session handling.
- `transport`: serial port I/O and fake transport for tests.
- `pids`: Mode 01 PID metadata and decoders.
- `dtc`: trouble-code parsing and definition lookup.
- `dashboard`: Streamlit live/replay dashboard.

## Local Setup

Install dependencies and run the test suite:

```powershell
uv sync --dev
uv run pytest
uv run ruff check .
```

If `uv` is not available on your shell path, the repo virtualenv works directly after `uv sync --dev` has created it:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest-cache-local\tmp -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check .
```

Start the MCP server over stdio:

```powershell
uv run obd-ii-mcp
```

For a paired Bluetooth dongle, Windows should expose one or more `Standard Serial over Bluetooth link` COM ports. The server can probe candidate COM ports automatically, or you can narrow probing with:

```powershell
$env:OBD_MCP_SERIAL_PORTS = "COM4,COM9"
uv run obd-ii-mcp
```

If you know the adapter's COM port, pinning it avoids slow or confusing probing:

```powershell
$env:OBD_MCP_SERIAL_PORTS = "COM4"
uv run obd-ii-mcp
```

The first hardware call to make from an MCP client is `obd_connect`. It sends only adapter-initialisation commands and does not clear codes or perform service actions. When you are done with the adapter, call `obd_disconnect` so another process can open the same COM port.

## Streamlit Dashboard

Run the live dashboard:

```powershell
$env:PYTHONPATH = "src"
$env:OBD_MCP_SERIAL_PORTS = "COM4"
Remove-Item Env:OBD_MCP_REPLAY_FILE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m streamlit run src\obd_ii_mcp\dashboard.py
```

Or use the installed script:

```powershell
uv run obd-ii-dashboard
```

The dashboard supports:

- live adapter mode
- replay file mode
- adapter connect/disconnect
- PID discovery
- decoded signal selection
- live metric cards
- Altair time-series charts
- recording live samples to `.obd-mcp/captures`
- renaming and loading capture files

Windows serial ports are exclusive. If Streamlit cannot connect to the adapter, another MCP server, Streamlit session, or Python process may still be holding the COM port. Use `obd_disconnect`, the dashboard **Disconnect** button, or stop the process that owns the adapter.

## Configuration

Expected configuration values:

| Name | Purpose |
| --- | --- |
| `OBD_MCP_SERIAL_PORTS` | Optional comma-separated list of COM ports to probe first, for example `COM4,COM9`. |
| `OBD_MCP_BAUD_RATES` | Optional comma-separated baud rates to try, default `38400,9600`. |
| `OBD_MCP_READ_TIMEOUT_MS` | Adapter read timeout. |
| `OBD_MCP_SESSION_DIR` | Directory for saved diagnostic session JSON files, default `.obd-mcp/sessions`. |
| `OBD_MCP_CAPTURE_DIR` | Directory for replayable live-data captures, default `.obd-mcp/captures`. |
| `OBD_MCP_REPLAY_FILE` | Optional path to a live-data capture JSON file. When set, the server fakes live PID reads from that file instead of probing serial ports. |
| `OBD_MCP_VEHICLE_PROFILE` | Optional vehicle profile, for example `vag`. |

## Live Data Replay

When you are in the car, record a short live-data capture:

```text
obd_record_live_data(pids=["0C", "0D", "05", "0F", "11", "42"], duration_seconds=30, interval_seconds=1)
```

That writes a JSON file under `.obd-mcp/captures`. Later, when the car or adapter is not available, point the server at that capture before startup:

```powershell
$env:OBD_MCP_REPLAY_FILE = ".obd-mcp/captures/20260509-194042-live-data.json"
uv run obd-ii-mcp
```

In replay mode, `obd_connect`, `obd_status`, `obd_live_data`, and `obd_sample_data` behave like a connected read-only vehicle session, cycling through the captured values over time.

Run the dashboard against a replay file:

```powershell
$env:PYTHONPATH = "src"
$env:OBD_MCP_REPLAY_FILE = ".obd-mcp\captures\<capture>.json"
.\.venv\Scripts\python.exe -m streamlit run src\obd_ii_mcp\dashboard.py
```

Replay mode is the easiest way to reproduce graphs and screenshots without sitting in the car.

## PID Discovery

`obd_discover_pids` asks the vehicle which standard Mode 01 PIDs it supports. Support discovery is separate from decoding:

- supported: the vehicle says it can answer this PID
- decoded: this project has a decoder for the response bytes
- undecoded: the vehicle supports it, but the app does not yet have a safe human-readable decoder

The decoder table currently covers the common live values plus the PIDs reported by the development vehicle, including status and enum values such as fuel system status, OBD standard, fuel type, and oxygen sensors present. Numeric values are chartable in the dashboard; text/status values appear as live values but are not plotted as lines.

## Troubleshooting

### Adapter Not Found

- Confirm the Bluetooth adapter is paired in Windows.
- Check which COM ports Windows created for the adapter.
- Set `OBD_MCP_SERIAL_PORTS` to the expected port, for example `COM4`.
- Make sure no other process is holding the port.

### Port Already In Use

Windows allows only one process to open a serial port at a time. If the MCP server connected first, Streamlit cannot also open the same COM port; if Streamlit connected first, MCP cannot also open it.

Release the adapter from the current owner:

- MCP: call `obd_disconnect`
- dashboard: click **Disconnect**
- development fallback: stop the Python process that owns the adapter

### Replay Keeps Loading Instead Of Live Mode

Live mode should clear `OBD_MCP_REPLAY_FILE`. In PowerShell:

```powershell
Remove-Item Env:OBD_MCP_REPLAY_FILE -ErrorAction SilentlyContinue
```

### Slow Or Confusing Port Probing

Pin the known port:

```powershell
$env:OBD_MCP_SERIAL_PORTS = "COM4"
```

## Development Notes

Cheap Bluetooth OBD-II adapters vary a lot in quality. The core diagnostic logic is tested with a fake transport, and real adapter quirks are kept in the transport/protocol layers.

For VAG-specific behaviour, the first useful layer is manufacturer-aware explanations and grouped context around generic OBD-II codes. Deeper VAG module scans may require protocols or tools beyond generic ELM327 OBD-II support, so that should be treated as a later milestone once the basic MCP server is reliable.

The `obd_probe_enhanced_protocols` and `obd_read_data_identifier` tools are intentionally narrow and read-only. They use UDS service `22` only against allow-listed identification DIDs such as VIN `F190`, ECU software number `F188`, ECU software version `F189`, and ECU hardware number `F191` on the engine ECU header. They do not expose arbitrary raw CAN commands or perform coding, adaptation, service resets, clearing codes, security access, write-data requests, or actuator tests.
