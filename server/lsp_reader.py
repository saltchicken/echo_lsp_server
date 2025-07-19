import asyncio
import json
import re
import sys
from typing import Optional, Dict


class LSPStreamReader:
    def __init__(self):
        self._reader = asyncio.StreamReader()

    async def setup(self):
        """Connect the internal StreamReader to stdin"""
        protocol = asyncio.StreamReaderProtocol(self._reader)
        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    async def read_message(self) -> Optional[Dict]:
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

