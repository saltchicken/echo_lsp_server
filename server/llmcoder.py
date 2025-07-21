import asyncio
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
import weakref

import httpx
from lsp_stream_io import LSPStreamIO


class LLMCoder:
    def __init__(self):
        self.running = True
        self.initialized = False
        self.document_store: Dict[str, List[str]] = {}
        self.io = LSPStreamIO()
        self.active_tasks: Set[asyncio.Task] = set()
        self.project_files: Dict[str, str] = {}  # key: file path, value: file content
        self.repo_root: Optional[str] = None

        log_dir = os.path.expanduser("~/.cache/nvim")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "llmcoder.log")

        with open(self.log_file, "w") as f:
            f.write(f"=== LLM Coder Server Started at {datetime.now()} ===\n")

    def log(self, message: str, level: str = "INFO") -> None:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"[{timestamp}] [{level}] {message}\n"
            with open(self.log_file, "a") as f:
                f.write(log_message)
        except Exception:
            print(f"[LLM Coder] {message}", file=sys.stderr, flush=True)

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
                    "serverInfo": {"name": "LLM Coder", "version": "1.0.0"},
                },
            }
        )
        self.initialized = True
        self.log("LSP Server initialized")

    async def handle_project_file(self, params: Dict[str, Any]):
        path = params.get("path")
        content = params.get("content")
        if not path or content is None:
            return

        self.repo_root = params.get("root")
        self.repo_root = os.path.basename(os.path.normpath(self.repo_root))
        self.log(f"Repo root set to: {self.repo_root}")
        self.project_files[self.repo_root + "/" + path] = content
        self.log(f"Stored project file: {path}")


    def build_repo_context(self) -> str:

        parts = [f"<|repo_name|>{self.repo_root}"]
        for path, content in self.project_files.items():
            parts.append(f"<|file_sep|>{path}\n{content}")
        return "\n".join(parts)


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

        PREFIX_CONTEXT_LINES = 30
        SUFFIX_CONTEXT_LINES = 30

        # Limit the context to 10 lines before and after
        prefix_lines = lines[max(0, line - PREFIX_CONTEXT_LINES) : line]
        suffix_lines = lines[line + 1 : line + 1 + SUFFIX_CONTEXT_LINES]


        prefix = "\n".join(prefix_lines) + "\n" + original[:character]
        suffix = original[character:] + "\n" + "\n".join(suffix_lines)

        repo_context = self.build_repo_context()




        full_prompt = (
            "<|fim_prefix|>\n" + prefix + "<|fim_suffix|>" + suffix + "\n<|fim_middle|>"
        )

        # full_prompt = repo_context + "\n" + full_prompt


        # def is_meaningful(text: str) -> bool:
        #     return bool(text.strip())
        #
        # if is_meaningful(suffix):
        #     self.log("Suffix contains content")
        #     full_prompt = (
        #         "<|fim_prefix|>\n" + prefix + "<|fim_suffix|>" + suffix + "\n<|fim_middle|>"
        #     )
        # else:
        #     self.log("Suffix is empty or only whitespace, removing it.")
        #     suffix = ""
        #     repo_name = "TEST REPO"
        #     file_path = "TEST PATH"
        #     file_content = "\n".join(lines)
        #     full_prompt = (
        #         f"<|repo_name|>{repo_name}\n<|file_sep|>{file_path}\n{file_content}"
        #     )



        def remove_suffix(text):
            max_len = min(len(text), len(suffix))
            for i in range(max_len, 0, -1):
                candidate = suffix[:i]
                if text.endswith(candidate):
                    return text[:-i]
            return text

        # Create and track the task
        async def ghost_text_task():
            try:
                processed = await self.query_external_api(full_prompt)
                if processed is False:
                    self.log("External API failed, not sending ghost text", "ERROR")
                    return
                processed = remove_suffix(processed)

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
            elif method == "custom/projectFile":
                await self.handle_project_file(message.get("params", {}))
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
        self.log("LLM Coder starting...")

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
        self.log("LLM Coder shutting down...")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    server = LLMCoder()
    try:
        loop.run_until_complete(server.run())
    finally:
        loop.close()
