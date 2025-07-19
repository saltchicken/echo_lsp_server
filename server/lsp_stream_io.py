# lsp_stream_io.py

import asyncio
import json
import re
import sys
from typing import Optional, Dict, Any


class LSPStreamIO:
    def __init__(self):
        self._reader = asyncio.StreamReader()

    async def setup(self):
        """Connect the internal StreamReader to stdin"""
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    async def read_message(self) -> Optional[Dict[str, Any]]:
        content_length = None

        while True:
            line = (await self._reader.readline()).decode("utf-8").strip()
            if not line:
                break
            match = re.match(r"Content-Length: (\d+)", line)
            if match:
                content_length = int(match.group(1))

        if content_length is None:
            return None

        body = await self._reader.readexactly(content_length)
        return json.loads(body.decode("utf-8"))

    async def send(self, payload: Dict[str, Any]) -> None:
        content = json.dumps(payload)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: sys.stdout.write(message))
        sys.stdout.flush()

    async def send_response(self, response: Dict[str, Any]) -> None:
        await self.send(response)

    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        await self.send({
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        })

