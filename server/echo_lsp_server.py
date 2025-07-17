import asyncio
import json
import re
import sys
import uuid
from typing import Any, Dict, Optional

class EchoLSPServer:
    def __init__(self):
        self.running = True
        self.reader = None
        self.tasks = {}  # Maps request ID or URI to task

    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] {message}", file=sys.stderr)

    async def read_message(self) -> Optional[Dict[str, Any]]:
        headers = {}
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if line == "\r\n" or line == "\n" or line == "":
                break
            match = re.match(r"([\w\-]+): (.+)", line)
            if match:
                headers[match.group(1)] = match.group(2)

        content_length = int(headers.get("Content-Length", 0))
        if content_length == 0:
            return None
        content = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.read, content_length)
        return json.loads(content)

    async def send_response(self, response: Dict[str, Any]) -> None:
        content = json.dumps(response)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        await asyncio.get_event_loop().run_in_executor(None, sys.stdout.write, message)
        sys.stdout.flush()

    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        content = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        await asyncio.get_event_loop().run_in_executor(None, sys.stdout.write, message)
        sys.stdout.flush()

    async def handle_initialize(self, message: Dict[str, Any]):
        result = {
            "capabilities": {
                "textDocumentSync": 1,
            }
        }
        await self.send_response({
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": result,
        })

    async def handle_trigger_ghost_text(self, message: Dict[str, Any]):
        uri = message["params"]["textDocument"]["uri"]
        request_id = str(message.get("id", uuid.uuid4()))
        self.log(f"Ghost request triggered for {uri} [{request_id}]")

        # Cancel previous if exists
        if uri in self.tasks:
            self.tasks[uri].cancel()

        # Start a new ghost generation task
        task = asyncio.create_task(self.do_ghost_text(uri, message))
        self.tasks[uri] = task

    async def do_ghost_text(self, uri: str, message: Dict[str, Any]):
        request_id = message.get("id")
        try:
            await asyncio.sleep(3)  # Simulate slow API
            text = "🌟 suggested code"
            await self.send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "text": text,
                },
            })
            self.log(f"Returned ghost text for {uri}")
        except asyncio.CancelledError:
            self.log(f"Ghost task cancelled for {uri}", "WARN")
            if request_id:
                await self.send_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32800,
                        "message": "Request cancelled",
                    },
                })

    async def handle_did_change(self, message: Dict[str, Any]):
        uri = message["params"]["textDocument"]["uri"]
        if uri in self.tasks:
            self.tasks[uri].cancel()
            self.log(f"Cancelled ghost text due to didChange on {uri}")

    async def handle_cancel_request(self, message: Dict[str, Any]):
        id_to_cancel = message.get("params", {}).get("id")
        for uri, task in self.tasks.items():
            if str(id_to_cancel) in str(task):  # crude match
                task.cancel()
                self.log(f"Cancelled task {id_to_cancel} for {uri}")
                break

    async def dispatch_message(self, message: Dict[str, Any]):
        method = message.get("method")
        if method == "initialize":
            await self.handle_initialize(message)
        elif method == "custom/triggerGhostText":
            await self.handle_trigger_ghost_text(message)
        elif method == "textDocument/didChange":
            await self.handle_did_change(message)
        elif method == "$/cancelRequest":
            await self.handle_cancel_request(message)

    async def run(self):
        self.log("Echo LSP Server starting...")
        while self.running:
            try:
                message = await self.read_message()
                if message is None:
                    break
                asyncio.create_task(self.dispatch_message(message))
            except Exception as e:
                self.log(f"Error: {e}", "ERROR")


if __name__ == "__main__":
    asyncio.run(EchoLSPServer().run())
