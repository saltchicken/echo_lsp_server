import asyncio
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
import weakref


class EchoLSPServer:
    def __init__(self):
        self.running = True
        self.initialized = False
        self.document_store: Dict[str, List[str]] = {}
        self.reader: Optional[asyncio.StreamReader] = None

        # Task tracking - choose one approach:

        # Approach 1: Track all active tasks
        self.active_tasks: Set[asyncio.Task] = set()

        # Approach 2: Track tasks by URI (for per-document cancellation)
        self.uri_tasks: Dict[str, Set[asyncio.Task]] = {}

        # Approach 3: Track tasks by request ID (for LSP cancellation)
        self.request_tasks: Dict[str, asyncio.Task] = {}

        log_dir = os.path.expanduser("~/.cache/nvim")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "echo_lsp.log")

        with open(self.log_file, "w") as f:
            f.write(f"=== Echo LSP Async Server Started at {datetime.now()} ===\n")

    def log(self, message: str, level: str = "INFO") -> None:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"[{timestamp}] [{level}] {message}\n"
            with open(self.log_file, "a") as f:
                f.write(log_message)
        except Exception:
            print(f"[Echo LSP] {message}", file=sys.stderr, flush=True)

    def add_task(
        self, task: asyncio.Task, uri: str = None, request_id: str = None
    ) -> None:
        """Add a task to tracking collections"""
        # Track in global set
        self.active_tasks.add(task)

        # Track by URI if provided
        if uri:
            if uri not in self.uri_tasks:
                self.uri_tasks[uri] = set()
            self.uri_tasks[uri].add(task)

        # Track by request ID if provided
        if request_id:
            self.request_tasks[request_id] = task

        # Clean up when task completes
        def cleanup_task(task_ref):
            task_obj = task_ref()
            if task_obj:
                self.active_tasks.discard(task_obj)
                if uri and uri in self.uri_tasks:
                    self.uri_tasks[uri].discard(task_obj)
                    if not self.uri_tasks[uri]:
                        del self.uri_tasks[uri]
                if request_id and request_id in self.request_tasks:
                    del self.request_tasks[request_id]

        # Use weak reference to avoid circular reference
        task_ref = weakref.ref(task, cleanup_task)
        task.add_done_callback(lambda t: cleanup_task(task_ref))

    def cancel_tasks_for_uri(self, uri: str) -> int:
        """Cancel all tasks for a specific URI"""
        if uri not in self.uri_tasks:
            return 0

        tasks_to_cancel = list(self.uri_tasks[uri])
        cancelled_count = 0

        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                cancelled_count += 1
                self.log(f"Cancelled task for URI: {uri}")

        return cancelled_count

    def cancel_task_by_request_id(self, request_id: str) -> bool:
        """Cancel a specific task by request ID"""
        if request_id in self.request_tasks:
            task = self.request_tasks[request_id]
            if not task.done():
                task.cancel()
                self.log(f"Cancelled task for request ID: {request_id}")
                return True
        return False

    def cancel_all_tasks(self) -> int:
        """Cancel all active tasks"""
        tasks_to_cancel = list(self.active_tasks)
        cancelled_count = 0

        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                cancelled_count += 1

        self.log(f"Cancelled {cancelled_count} tasks")
        return cancelled_count

    def get_task_stats(self) -> Dict[str, Any]:
        """Get current task statistics"""
        return {
            "total_active_tasks": len(self.active_tasks),
            "tasks_by_uri": {uri: len(tasks) for uri, tasks in self.uri_tasks.items()},
            "request_tasks": len(self.request_tasks),
            "running_tasks": len([t for t in self.active_tasks if not t.done()]),
            "completed_tasks": len([t for t in self.active_tasks if t.done()]),
        }

    async def send_response(self, response: Dict[str, Any]) -> None:
        content = json.dumps(response)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: sys.stdout.write(message))
        sys.stdout.flush()

    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        await self.send_response({"jsonrpc": "2.0", "method": method, "params": params})

    async def send_ghost_text(self, uri: str, line: int, text: str) -> None:
        await self.send_notification(
            "ghostText/virtualText",
            {
                "uri": uri,
                "line": line,
                "text": f"👻 {text}",
            },
        )

    async def read_message(self) -> Optional[Dict[str, Any]]:
        content_length = None

        while True:
            line = (await self.reader.readline()).decode("utf-8").strip()
            if not line:
                break
            match = re.match(r"Content-Length: (\d+)", line)
            if match:
                content_length = int(match.group(1))

        if content_length is None:
            return None

        body = await self.reader.readexactly(content_length)
        return json.loads(body.decode("utf-8"))

    async def query_external_api(self, input_text: str) -> str:
        """Simulated async external API call"""
        try:
            await asyncio.sleep(1)  # simulate latency
            return f"Processed: {input_text[::-1]}"  # reverse the input for demo
        except asyncio.CancelledError:
            self.log("External API query was cancelled")
            raise

    async def handle_initialize(self, request: Dict[str, Any]) -> None:
        capabilities = {
            "hoverProvider": True,
            "textDocumentSync": {
                "openClose": True,
                "change": 1,
                "save": True,
            },
            "experimental": {"ghostTextProvider": True},
        }

        await self.send_response(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "capabilities": capabilities,
                    "serverInfo": {"name": "Echo Async LSP", "version": "1.0.0"},
                },
            }
        )
        self.initialized = True
        self.log("Server initialized")

    async def handle_hover(self, request: Dict[str, Any]) -> None:
        params = request["params"]
        uri = params["textDocument"]["uri"]
        line_number = params["position"]["line"]

        result = None
        if uri in self.document_store:
            lines = self.document_store[uri]
            if 0 <= line_number < len(lines):
                current_line = lines[line_number]
                result = {
                    "contents": {
                        "kind": "markdown",
                        "value": f"**Echo**\n\n`{current_line}`",
                    },
                    "range": {
                        "start": {"line": line_number, "character": 0},
                        "end": {"line": line_number, "character": len(current_line)},
                    },
                }

        await self.send_response(
            {"jsonrpc": "2.0", "id": request["id"], "result": result}
        )

    async def handle_trigger_ghost_text(self, request: Dict[str, Any]) -> None:
        params = request["params"]
        uri = params["textDocument"]["uri"]
        line = params["position"]["line"]
        request_id = str(request["id"])

        await self.send_response(
            {"jsonrpc": "2.0", "id": request["id"], "result": {"ack": True}}
        )

        if uri not in self.document_store:
            self.log(f"Ghost request: doc not found {uri}")
            return

        self.log(f"URI: {uri}")

        lines = self.document_store[uri]
        if not (0 <= line < len(lines)):
            self.log(f"Ghost request: line out of range {line}")
            return

        original = lines[line]

        # Create and track the task
        async def ghost_text_task():
            try:
                processed = await self.query_external_api(original)
                await self.send_ghost_text(uri, line, processed)
                self.log(f"Ghost text sent for line {line + 1}")
            except asyncio.CancelledError:
                self.log(f"Ghost text task cancelled for line {line + 1}")
                raise
            except Exception as e:
                self.log(f"Ghost text error: {e}", "ERROR")

        task = asyncio.create_task(ghost_text_task())
        self.add_task(task, uri=uri, request_id=request_id)

    async def handle_cancel_request(self, message: Dict[str, Any]):
        """Handle LSP cancel request"""
        self.log("Cancel request received")
        params = message.get("params", {})
        request_id = params.get("id")

        if request_id:
            # Try to cancel by request ID
            if self.cancel_task_by_request_id(str(request_id)):
                self.log(f"Cancelled task for request ID: {request_id}")
            else:
                self.log(f"No task found for request ID: {request_id}")
        else:
            # Cancel all tasks if no specific ID
            cancelled = self.cancel_all_tasks()
            self.log(f"Cancelled {cancelled} tasks")

    async def handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        if method == "initialized":
            self.initialized = True
        elif method == "textDocument/didOpen":
            uri = params["textDocument"]["uri"]
            text = params["textDocument"]["text"]
            self.document_store[uri] = text.splitlines()
        elif method == "textDocument/didChange":
            uri = params["textDocument"]["uri"]
            text = params["contentChanges"][0]["text"]
            self.document_store[uri] = text.splitlines()

            # Optionally cancel existing tasks for this URI on change
            cancelled = self.cancel_tasks_for_uri(uri)
            if cancelled > 0:
                self.log(f"Cancelled {cancelled} tasks for changed document: {uri}")

        elif method == "textDocument/didClose":
            uri = params["textDocument"]["uri"]
            if uri in self.document_store:
                del self.document_store[uri]

            # Cancel all tasks for the closed document
            cancelled = self.cancel_tasks_for_uri(uri)
            if cancelled > 0:
                self.log(f"Cancelled {cancelled} tasks for closed document: {uri}")

    async def dispatch_message(self, message: Dict[str, Any]) -> None:
        try:
            method = message.get("method")
            if method:
                self.log(method)
            else:
                self.log("Method was missing", "ERROR")
            if method == "initialize":
                await self.handle_initialize(message)
            elif method == "textDocument/hover":
                await self.handle_hover(message)
            elif method == "custom/triggerGhostText":
                await self.handle_trigger_ghost_text(message)
            elif method in {
                "initialized",
                "textDocument/didOpen",
                "textDocument/didChange",
                "textDocument/didClose",
            }:
                await self.handle_notification(method, message.get("params", {}))
            elif method == "$/cancelGhostText":
                await self.handle_cancel_request(message)
            elif method == "shutdown":
                # Cancel all tasks on shutdown
                self.cancel_all_tasks()
                await self.send_response(
                    {"jsonrpc": "2.0", "id": message["id"], "result": None}
                )
            elif method == "exit":
                self.running = False
        except Exception as e:
            self.log(f"Dispatch error: {e}", "ERROR")
            if "id" in message:
                await self.send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "error": {
                            "code": -32603,
                            "message": "Internal server error",
                            "data": str(e),
                        },
                    }
                )

    async def run(self) -> None:
        self.log("Async Echo LSP Server starting...")

        self.reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self.reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        while self.running:
            try:
                message = await self.read_message()
                if message is None:
                    break

                # Create task for message handling (not tracked since it's internal)
                asyncio.create_task(self.dispatch_message(message))

                # Periodically log task stats (optional)
                if hasattr(self, "_last_stats_log"):
                    if (
                        datetime.now().timestamp() - self._last_stats_log > 30
                    ):  # every 30 seconds
                        stats = self.get_task_stats()
                        self.log(f"Task stats: {stats}")
                        self._last_stats_log = datetime.now().timestamp()
                else:
                    self._last_stats_log = datetime.now().timestamp()

            except Exception as e:
                self.log(f"Main loop error: {e}", "ERROR")

        # Clean up remaining tasks
        self.cancel_all_tasks()
        self.log("Async Echo LSP Server shutting down...")


if __name__ == "__main__":
    asyncio.run(EchoLSPServer().run())
