import base64
import json
import os
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

SPOOL = "/var/lib/sg/pending"


class Handler(BaseHTTPRequestHandler):
    def _body(self) -> bytes:
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = []
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    return b"".join(chunks)
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _record(self) -> None:
        record = {
            "method": self.command,
            "host": self.headers.get("Host", ""),
            "address": self.connection.getsockname()[0],
            "path": self.path,
            "body": base64.b64encode(self._body()).decode(),
        }
        with open(os.path.join(SPOOL, f"{time.time_ns()}-{threading.get_ident()}.json"), "w") as f:
            json.dump(record, f)
        payload = b'{"status": "accepted"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = _record

    def log_message(self, *args) -> None:
        pass


class Server(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


Server(("0.0.0.0", 80), Handler).serve_forever()
