# obd-ii-mcp

An MCP server for interrogating and gaining insights from a Bluetooth OBD-II scanner, with an initial focus on cheap VAG-compatible dongles and ELM327-style adapters.

The goal is to let Claude, Codex, or any MCP-capable client safely talk to a car through a local server. The server should handle the low-level adapter session, expose a small set of diagnostic tools, and return structured data that an AI assistant can reason over without needing direct access to the vehicle bus.

## What This Should Do

- Connect to a paired Bluetooth OBD-II adapter.
- Detect and initialise the adapter protocol.
- Read live vehicle data such as RPM, coolant temperature, intake air temperature, vehicle speed, fuel trim, oxygen sensor values, and battery voltage.
- Pull stored, pending, and permanent diagnostic trouble codes.
- Decode common generic OBD-II fault codes.
- Add manufacturer-aware context where possible, starting with VAG vehicles.
- Capture time-series samples around a fault or symptom.
- Produce graph-ready diagnostic data for MCP clients.
- Optionally clear fault codes only when explicitly enabled and confirmed.

## MCP Tool Surface

The first version should expose a conservative set of tools:

| Tool | Purpose |
| --- | --- |
| `obd_connect` | Connect to a configured Bluetooth adapter and initialise the OBD session. |
| `obd_status` | Report adapter connection, vehicle protocol, VIN availability, and session health. |
| `obd_read_codes` | Read stored, pending, and permanent DTCs. |
| `obd_decode_code` | Explain a DTC using built-in generic definitions and any available manufacturer notes. |
| `obd_live_data` | Read one or more supported PIDs once. |
| `obd_sample_data` | Sample selected PIDs over time and return graph-ready series data. |
| `obd_fault_snapshot` | Pull codes plus relevant live data in one diagnostic bundle. |

Write/service tools such as clearing codes are intentionally deferred until after the read-only hardware path is reliable.

## Safety Boundaries

This project should default to read-only behaviour. Anything that changes vehicle state must be gated behind configuration and require an explicit tool call. The server should avoid exposing arbitrary raw CAN writes as an MCP tool.

Initial safety rules:

- Read-only mode is the default.
- Clearing codes and other write/service actions are not implemented in v1.
- Raw adapter commands are not exposed to MCP clients by default.
- Tool responses should make uncertainty clear rather than over-diagnosing.
- The server should never claim that a fault code alone proves a component has failed.

## Architecture Plan

```text
MCP client
  -> MCP server
    -> OBD service layer
      -> adapter transport
        -> Bluetooth serial port
          -> ELM327 / OBD-II adapter
            -> vehicle ECU
```

Suggested internal modules:

- `server`: MCP server bootstrap and tool registration.
- `obd`: high-level diagnostic operations.
- `transport`: Bluetooth serial connection handling.
- `protocol`: ELM327 command/session handling and OBD-II PID parsing.
- `dtc`: trouble-code parsing and definition lookup.
- `sampling`: time-series collection for graph-ready responses.

## Local Setup

Install dependencies and run the test suite:

```powershell
uv sync --dev
uv run pytest
uv run ruff check .
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

The first hardware call to make from an MCP client is `obd_connect`. It sends only adapter-initialisation commands in v1 and does not clear codes or perform service actions.

## Configuration

Expected configuration values:

| Name | Purpose |
| --- | --- |
| `OBD_MCP_SERIAL_PORTS` | Optional comma-separated list of COM ports to probe first, for example `COM4,COM9`. |
| `OBD_MCP_BAUD_RATES` | Optional comma-separated baud rates to try, default `38400,9600`. |
| `OBD_MCP_READ_TIMEOUT_MS` | Adapter read timeout. |
| `OBD_MCP_SESSION_DIR` | Directory for saved diagnostic session JSON files, default `.obd-mcp/sessions`. |
| `OBD_MCP_VEHICLE_PROFILE` | Optional vehicle profile, for example `vag`. |

## First Milestone

- [x] Choose the implementation stack and MCP SDK.
- [x] Add the MCP server entry point.
- [x] Implement adapter configuration and connection status.
- [x] Implement a mock transport for development without the car attached.
- [x] Implement ELM327 initialisation commands.
- [x] Implement reading and parsing generic DTCs.
- [x] Implement basic PID reads for live data.
- [x] Return graph-ready sampled PID data.
- [x] Add tests for DTC parsing and PID decoding.
- [x] Document local setup with the Bluetooth dongle.

## Development Notes

Cheap Bluetooth OBD-II adapters vary a lot in quality. We should build the project so the core diagnostic logic can be tested with a mock transport, then keep real adapter quirks isolated in the transport/protocol layers.

For VAG-specific behaviour, the first useful layer is manufacturer-aware explanations and grouped context around generic OBD-II codes. Deeper VAG module scans may require protocols or tools beyond generic ELM327 OBD-II support, so that should be treated as a later milestone once the basic MCP server is reliable.
