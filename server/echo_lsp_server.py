"""
Simple Echo LSP Server for Neovim
This LSP server echoes the current line as hover information and supports ghost text.
"""

import json
import sys
import re
import os
from datetime import datetime
from typing import Dict, Any, Optional, List


class EchoLSPServer:
    def __init__(self):
        self.running = True
        self.initialized = False
        self.document_store: Dict[str, List[str]] = {}

        # Set up file logging
        log_dir = os.path.expanduser("~/.cache/nvim")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "echo_lsp.log")

        # Clear previous log on startup
        with open(self.log_file, "w") as f:
            f.write(f"=== Echo LSP Server Started at {datetime.now()} ===\n")

    def log(self, message: str, level: str = "INFO") -> None:
        """Log messages to file for debugging"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"[{timestamp}] [{level}] {message}\n"
            with open(self.log_file, "a") as f:
                f.write(log_message)
        except Exception:
            # Fallback to stderr if file logging fails
            print(f"[Echo LSP] {message}", file=sys.stderr, flush=True)

    def send_response(self, response: Dict[str, Any]) -> None:
        """Send a JSON-RPC response to the client"""
        content = json.dumps(response)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        sys.stdout.write(message)
        sys.stdout.flush()

    def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a notification to the client"""
        response = {"jsonrpc": "2.0", "method": method, "params": params}
        self.send_response(response)

    def send_ghost_text(self, uri: str, line: int, text: str) -> None:
        """Send ghost text notification to the client"""
        self.send_notification(
            "ghostText/virtualText",
            {
                "uri": uri,
                "line": line,
                "text": f"👻 {text}",  # Add ghost emoji for visual indication
            },
        )

    def handle_initialize(self, request: Dict[str, Any]) -> None:
        """Handle the initialize request"""
        capabilities = {
            "hoverProvider": True,
            "textDocumentSync": {
                "openClose": True,
                "change": 1,  # Full document sync
                "save": True,
            },
        }

        response = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "capabilities": capabilities,
                "serverInfo": {"name": "Echo LSP Server", "version": "1.0.0"},
            },
        }
        self.send_response(response)
        self.log("Server initialized with hover capabilities")

    def handle_initialized(self, request: Dict[str, Any]) -> None:
        """Handle the initialized notification"""
        self.initialized = True
        self.log("Server initialization completed")

    def handle_text_document_did_open(self, params: Dict[str, Any]) -> None:
        """Handle document open event"""
        doc = params["textDocument"]
        uri = doc["uri"]
        text = doc["text"]
        self.document_store[uri] = text.split("\n")
        self.log(f"Document opened: {uri}")

    def handle_text_document_did_change(self, params: Dict[str, Any]) -> None:
        """Handle document change event"""
        uri = params["textDocument"]["uri"]
        changes = params["contentChanges"]

        # For full document sync, we replace the entire content
        if changes and "text" in changes[0]:
            self.document_store[uri] = changes[0]["text"].split("\n")
            self.log(f"Document updated: {uri}")

    def handle_text_document_did_close(self, params: Dict[str, Any]) -> None:
        """Handle document close event"""
        uri = params["textDocument"]["uri"]
        if uri in self.document_store:
            del self.document_store[uri]
        self.log(f"Document closed: {uri}")

    def handle_hover(self, request: Dict[str, Any]) -> None:
        """Handle hover request - echo the current line"""
        params = request["params"]
        uri = params["textDocument"]["uri"]
        position = params["position"]
        line_number = position["line"]

        response = {"jsonrpc": "2.0", "id": request["id"], "result": None}

        if uri in self.document_store:
            lines = self.document_store[uri]
            if 0 <= line_number < len(lines):
                current_line = lines[line_number]
                hover_content = {
                    "kind": "markdown",
                    "value": f"**Echo LSP Server**\n\nCurrent line ({line_number + 1}): `{current_line}`",
                }
                response["result"] = {
                    "contents": hover_content,
                    "range": {
                        "start": {"line": line_number, "character": 0},
                        "end": {"line": line_number, "character": len(current_line)},
                    },
                }
                self.log(f"Hover response for line {line_number + 1}: {current_line}")
            else:
                self.log(f"Line {line_number} out of range")
        else:
            self.log(f"Document not found: {uri}")

        self.send_response(response)

    def handle_trigger_ghost_text(self, request: Dict[str, Any]) -> None:
        """Handle custom ghost text trigger request"""
        params = request["params"]
        uri = params["textDocument"]["uri"]
        position = params["position"]
        line_number = position["line"]

        response = {"jsonrpc": "2.0", "id": request["id"], "result": None}

        if uri in self.document_store:
            lines = self.document_store[uri]
            if 0 <= line_number < len(lines):
                current_line = lines[line_number]

                # Send ghost text notification
                self.send_ghost_text(uri, line_number, current_line)

                # Send success response
                response["result"] = {"success": True}
                self.log(
                    f"Ghost text triggered for line {line_number + 1}: {current_line}"
                )
            else:
                response["error"] = {
                    "code": -32602,
                    "message": f"Line {line_number} out of range",
                }
                self.log(f"Ghost text trigger failed: Line {line_number} out of range")
        else:
            response["error"] = {
                "code": -32602,
                "message": f"Document not found: {uri}",
            }
            self.log(f"Ghost text trigger failed: Document not found: {uri}")

        self.send_response(response)

    def handle_shutdown(self, request: Dict[str, Any]) -> None:
        """Handle shutdown request"""
        response = {"jsonrpc": "2.0", "id": request["id"], "result": None}
        self.send_response(response)
        self.log("Shutdown request received")

    def handle_exit(self, request: Dict[str, Any]) -> None:
        """Handle exit notification"""
        self.running = False
        self.log("Exit notification received")

    def parse_header(self, line: str) -> Optional[int]:
        """Parse Content-Length from header"""
        match = re.match(r"Content-Length: (\d+)", line)
        return int(match.group(1)) if match else None

    def read_message(self) -> Optional[Dict[str, Any]]:
        """Read a JSON-RPC message from stdin"""
        try:
            # Read headers
            content_length = None
            while True:
                line = sys.stdin.buffer.readline().decode("utf-8")
                if not line:
                    return None

                line = line.strip()
                if not line:  # Empty line indicates end of headers
                    break

                length = self.parse_header(line)
                if length is not None:
                    content_length = length

            if content_length is None:
                self.log("No Content-Length header found")
                return None

            # Read exactly content_length bytes from buffer
            content_bytes = sys.stdin.buffer.read(content_length)
            if len(content_bytes) != content_length:
                self.log(f"Expected {content_length} bytes, got {len(content_bytes)}")
                return None

            # Decode to string
            content = content_bytes.decode("utf-8")

            self.log(
                f"Received message length: {len(content)} chars, {len(content_bytes)} bytes"
            )

            # Parse JSON
            message = json.loads(content)
            return message

        except (json.JSONDecodeError, ValueError) as e:
            self.log(f"Error parsing message: {e}")
            self.log(
                f"Content length: {content_length if 'content_length' in locals() else 'Unknown'}"
            )
            if "content" in locals():
                self.log(f"Content preview: {repr(content[:200])}")
                self.log(f"Content end: {repr(content[-50:])}")
            return None
        except UnicodeDecodeError as e:
            self.log(f"Unicode decode error: {e}")
            return None
        except EOFError:
            self.log("EOF reached")
            return None

    def handle_request(self, request: Dict[str, Any]) -> None:
        """Handle incoming JSON-RPC request"""
        method = request.get("method")
        self.log(f"Method: {method}")

        if method == "initialize":
            self.handle_initialize(request)
        elif method == "initialized":
            self.handle_initialized(request)
        elif method == "textDocument/didOpen":
            self.handle_text_document_did_open(request["params"])
        elif method == "textDocument/didChange":
            self.handle_text_document_did_change(request["params"])
        elif method == "textDocument/didClose":
            self.handle_text_document_did_close(request["params"])
        elif method == "textDocument/hover":
            self.handle_hover(request)
        elif method == "custom/triggerGhostText":
            self.handle_trigger_ghost_text(request)
        elif method == "shutdown":
            self.handle_shutdown(request)
        elif method == "exit":
            self.handle_exit(request)
        else:
            # Send method not found error for unhandled requests with IDs
            if "id" in request:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {
                        "code": -32601,
                        "message": "Method not found",
                        "data": method,
                    },
                }
                self.send_response(error_response)

    def run(self) -> None:
        """Main server loop"""
        self.log("Echo LSP Server starting...")

        while self.running:
            try:
                message = self.read_message()
                if message is None:
                    break

                self.handle_request(message)

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"Unexpected error: {e}", "ERROR")
                break

        self.log("Echo LSP Server shutting down...")


if __name__ == "__main__":
    server = EchoLSPServer()
    server.run()
