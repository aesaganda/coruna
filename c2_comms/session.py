import asyncio
import uuid
from datetime import datetime

class Session:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, peername: tuple, session_type: str = "unknown"):
        self.id: str = str(uuid.uuid4())[:8] # Short ID for easy reference
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self.ip_address: str = peername[0]
        self.port: int = peername[1]
        self.connected_at: datetime = datetime.now()
        self.status: str = "active" # Can be "active", "backgrounded", "terminated"
        self.type: str = session_type # E.g.: "basic_sandbox_shell", "full_access_shell"
        self.output_buffer: list = [] # Buffer to store shell output
        self.current_command: str = "" # Command currently being executed

    def to_dict(self):
        return {
            "id": self.id,
            "ip_address": self.ip_address,
            "port": self.port,
            "connected_at": self.connected_at.strftime("%Y-%m-%d %H:%M:%S"),
            "status": self.status,
            "type": self.type
        }

    async def send_command(self, command: str):
        """Sends command to remote shell (appends \\n)."""
        self.current_command = command
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
                self.output_buffer.append(text)
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