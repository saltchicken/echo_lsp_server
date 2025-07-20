import asyncio
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
import weakref

# import requests
import httpx
from lsp_stream_io import LSPStreamIO


class EchoLSPServer:
    def __init__(self):
        self.running = True
        self.initialized = False
        self.document_store: Dict[str, List[str]] = {}
        self.io = LSPStreamIO()
        self.active_tasks: Set[asyncio.Task] = set()

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

    def add_task(self, task: asyncio.Task) -> None:
        """Add a task to tracking collections"""
        self.active_tasks.add(task)

        def cleanup_task(task_ref):
            task_obj = task_ref()
            if task_obj:
                self.active_tasks.discard(task_obj)

        # Use weak reference to avoid circular reference
        task_ref = weakref.ref(task, cleanup_task)
        task.add_done_callback(lambda t: cleanup_task(task_ref))

    def cancel_all_tasks(self) -> int:
        """Cancel all active tasks"""
        tasks_to_cancel = list(self.active_tasks)
        cancelled_count = 0

        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                cancelled_count += 1

        return cancelled_count

    async def send_ghost_text(self, uri: str, line: int, text: str) -> None:
        await self.io.send_notification(
            "ghostText/virtualText",
            {
                "uri": uri,
                "line": line,
                "text": text,
            },
        )

    async def query_external_api(self, prompt: str) -> str | bool:
        """Query external LLM API asynchronously using httpx. Returns False on failure."""
        try:
            payload = {
                "prompt": prompt,
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post("http://main:8000/generate", json=payload)
                if response.status_code != 200:
                    self.log(
                        f"API returned status {response.status_code}: {response.text}",
                        "ERROR",
                    )

                response.raise_for_status()
                return response.text or False

        except asyncio.CancelledError:
            self.log("External API query was cancelled")
            raise

        except Exception as e:
            self.log(f"query_external_api error: {repr(e)}", "ERROR")
            return False

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

        await self.io.send_response(
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
        self.log("LSP Server initialized")

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

        await self.io.send_response(
            {"jsonrpc": "2.0", "id": request["id"], "result": result}
        )

    async def handle_trigger_ghost_text(self, request: Dict[str, Any]) -> None:
        params = request["params"]
        uri = params["textDocument"]["uri"]
        line = params["position"]["line"]
        character = params["position"]["character"]
        # request_id = str(request["id"])

        # TODO: I don't believe this is needed
        await self.io.send_response(
            {"jsonrpc": "2.0", "id": request["id"], "result": {"ack": True}}
        )

        if uri not in self.document_store:
            self.log(f"Ghost request: doc not found {uri}")
            return

        lines = self.document_store[uri]
        if not (0 <= line < len(lines)):
            self.log(f"Ghost request: line out of range {line}")
            return

        if len(self.active_tasks) > 0:
            self.log("There is already an active task. Disregarding")
            return

        original = lines[line]
        if not (0 <= character <= len(original)):
            self.log(f"Ghost request: character position out of range {character}")
            return

        # Limit the context to 10 lines before and after
        prefix_lines = lines[max(0, line - 10) : line]
        suffix_lines = lines[line + 1 : line + 11]

        prefix = "\n".join(prefix_lines) + "\n" + original[:character]
        suffix = original[character:] + "\n" + "\n".join(suffix_lines)

        full_prompt = (
            "<|fim_prefix|>\n" + prefix + "<|fim_suffix|>" + suffix + "\n<|fim_middle|>"
        )

        # Create and track the task
        async def ghost_text_task():
            try:
                processed = await self.query_external_api(full_prompt)
                if processed is False:
                    self.log("External API failed, not sending ghost text", "ERROR")
                    return
                processed = processed.strip()
                await self.send_ghost_text(uri, line, processed)
                self.log(f"Ghost text sent for line {line + 1}")
            except asyncio.CancelledError:
                self.log(f"Ghost text task cancelled for line {line + 1}")
                raise
            except Exception as e:
                self.log(f"Ghost text error: {e}", "ERROR")

        task = asyncio.create_task(ghost_text_task())
        self.add_task(task)

    async def handle_cancel_request(self, message: Dict[str, Any]):
        """Handle LSP cancel request"""
        # self.log("Cancel request received")
        # params = message.get("params", {})
        cancelled = self.cancel_all_tasks()
        # self.log(f"Cancelled {cancelled} tasks")

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
            # TODO: Check this out
            cancelled = self.cancel_all_tasks()
            if cancelled > 0:
                self.log("This happened")

        elif method == "textDocument/didClose":
            uri = params["textDocument"]["uri"]
            if uri in self.document_store:
                del self.document_store[uri]

            # Cancel all tasks for the closed document
            # cancelled = self.cancel_tasks_for_uri(uri)
            # if cancelled > 0:
            #     self.log(f"Cancelled {cancelled} tasks for closed document: {uri}")

    async def dispatch_message(self, message: Dict[str, Any]) -> None:
        try:
            method = message.get("method")
            # if method:
            #     self.log(method)
            # else:
            #     self.log("Method was missing", "ERROR")
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
                # await self.io.send_response(
                #     {"jsonrpc": "2.0", "id": message["id"], "result": None}
                # )
            elif method == "exit":
                self.running = False
        except Exception as e:
            self.log(f"Dispatch error: {e}", "ERROR")
            if "id" in message:
                await self.io.send_response(
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

        await self.io.setup()

        while self.running:
            try:
                message = await self.io.read_message()
                if message is None:
                    break

                asyncio.create_task(self.dispatch_message(message))

            except Exception as e:
                self.log(f"Main loop error: {e}", "ERROR")

        # Clean up remaining tasks
        self.cancel_all_tasks()
        self.log("Async Echo LSP Server shutting down...")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    server = EchoLSPServer()
    try:
        loop.run_until_complete(server.run())
    finally:
        loop.close()
