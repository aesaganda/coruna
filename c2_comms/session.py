import asyncio
import uuid
from datetime import datetime
from typing import Callable, List, Optional


class Session:
    MAX_TRANSCRIPT_ENTRIES = 2000

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peername: tuple,
        session_type: str = "unknown",
        on_command_cb: Optional[Callable] = None,
    ):
        self.id: str = str(uuid.uuid4())[:8]  # Short ID for easy reference
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self.ip_address: str = peername[0]
        self.port: int = peername[1]
        self.connected_at: datetime = datetime.now()
        self.last_activity: datetime = self.connected_at
        self.disconnected_at: Optional[datetime] = None
        self.status: str = "active"  # Can be "active", "backgrounded", "terminated"
        self.type: str = session_type  # E.g.: "basic_sandbox_shell", "full_access_shell"
        self.output_buffer: list = []  # Buffer to store shell output (used by CLI)
        self.transcript: List[dict] = []  # Persistent transcript for Web UI
        self.current_command: str = ""  # Command currently being executed
        self.commands_sent: int = 0
        self.bytes_received: int = 0
        self._on_command_cb = on_command_cb

    def append_transcript(self, kind: str, text: str, source: str = "remote") -> dict:
        self.last_activity = datetime.now()
        entry = {
            "timestamp": self.last_activity.strftime("%H:%M:%S.%f")[:-3],
            "iso_time": self.last_activity.isoformat(),
            "kind": kind,
            "text": text,
            "source": source,
        }
        self.transcript.append(entry)
        if len(self.transcript) > self.MAX_TRANSCRIPT_ENTRIES:
            self.transcript = self.transcript[-self.MAX_TRANSCRIPT_ENTRIES :]
        return entry

    def record_output(self, text: str) -> dict:
        self.output_buffer.append(text)
        self.bytes_received += len(text.encode("utf-8", errors="replace"))
        return self.append_transcript("output", text, source="remote")

    def to_dict(self):
        return {
            "id": self.id,
            "ip_address": self.ip_address,
            "port": self.port,
            "connected_at": self.connected_at.strftime("%Y-%m-%d %H:%M:%S"),
            "last_activity": self.last_activity.strftime("%Y-%m-%d %H:%M:%S"),
            "disconnected_at": (
                self.disconnected_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.disconnected_at
                else None
            ),
            "status": self.status,
            "type": self.type,
            "commands_sent": self.commands_sent,
            "bytes_received": self.bytes_received,
            "current_command": self.current_command,
        }

    async def send_command(self, command: str, source: str = "cli"):
        """Sends command to remote shell (appends \\n)."""
        self.current_command = command
        self.commands_sent += 1
        entry = self.append_transcript("input", command + "\n", source=source)
        if self._on_command_cb:
            try:
                res = self._on_command_cb(self, command, entry)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass
        try:
            self.writer.write((command + "\n").encode())
            await self.writer.drain()
        except Exception as e:
            raise RuntimeError(f"Error sending command: {e}") from e

    async def read_output(self, timeout: float = 0.5) -> str:
        """Reads available data from reader and appends to buffer. Returns read text."""
        try:
            data = await asyncio.wait_for(self.reader.read(65536), timeout=timeout)
            if data:
                text = data.decode("utf-8", errors="replace")
                self.record_output(text)
                return text
        except asyncio.TimeoutError:
            pass
        except Exception:
            raise
        return ""

    def get_buffered_output(self) -> str:
        """Returns and clears the output buffer."""
        out = "".join(self.output_buffer)
        self.output_buffer.clear()
        return out

    async def close(self):
        """Closes the underlying session stream."""
        self.status = "terminated"
        if not self.disconnected_at:
            self.disconnected_at = datetime.now()
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
