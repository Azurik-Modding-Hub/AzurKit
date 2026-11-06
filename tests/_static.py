"""A site's folder served on 127.0.0.1 from a process of its own (``tests/_page.py``'s :class:`Served`, the site's
tests' host), so a page's files never wait on the test's own interpreter: a test process busy beside a page (a plan in
an app test's thread, a full collection of a heap a randomizer test left) held the files it served there in its GIL,
on GitHub's 4-core Intel runner 98 s for one 17 KB picture (run 42071325305). Standard library only, run with ``-I``.

``python -I _static.py ROOT TYPES [--pages]``: ``TYPES`` the app's ``Content-Type`` by suffix (JSON). It prints its port,
then answers a GET or HEAD of a file under the root (``/`` is ``index.html``) with its bytes, its type and length and no
validator, as the site's routes did; with ``--pages`` as GitHub Pages does, ``Cache-Control: max-age=600`` and
``Last-Modified`` too, every answer whole (no 304). Anything else is a 404 (another method a 405, which closes its
connection). It keeps each connection for the next request (HTTP/1.1) and sends without Nagle's delay, as GitHub Pages
serves a page's files over a few kept connections, never one a file: a first visit's install asks for its release's
551 files, which took one loopback connection each and passed its 60 s on GitHub's Windows runner (run 42236789239),
where the page's second engine, a few big files, loaded in 2.9 s. Each request is logged. It reads commands on stdin,
one line each, and answers each with one line: ``root PATH`` (a deploy: serve that folder from now on), ``down 1`` or
``down 0`` (each answer a 503 while down), ``log`` (every request so far, JSON: ``[method, path, body bytes]``),
``heard SECONDS PATH`` (``heard`` once a request for ``PATH``, with its query, is logged, at once if one was, else
``unheard`` past ``SECONDS``: the answer a test reads with its interpreter held, ``_page.Served.held``). It ends when
stdin closes."""

from __future__ import annotations

import email.utils
import http.server
import json
import socket
import sys
import threading
import urllib.parse
from pathlib import Path


class Files(http.server.ThreadingHTTPServer):
    """Its listen queue the system's longest (``socket.SOMAXCONN``), not socketserver's 5: a page's load asks for
    about 33 files at once, and Windows refuses a connect past a full queue where macOS and Linux drop it and the client
    tries again (29 site tests failed so on Windows, ECONNREFUSED, run 41666183947)."""
    request_queue_size = socket.SOMAXCONN
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        """A browser that closed a kept connection (a context's close resets them) or left mid-answer is no fault of
        the host's: only another error prints its traceback."""
        if not isinstance(sys.exception(), ConnectionError):
            super().handle_error(request, client_address)


def main(argv: list[str]) -> None:
    types, pages = json.loads(argv[2]), "--pages" in argv[3:]
    state, log, lock = {"root": Path(argv[1]).resolve(), "down": False}, [], threading.Condition()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"   # kept connections, as GitHub Pages keeps its, never one a file
        disable_nagle_algorithm = True  # TCP_NODELAY: an answer's body never waits on the client's ACK of its headers

        def log_message(self, *args) -> None:
            pass

        def _heard(self) -> tuple[Path, bool]:
            with lock:
                log.append([self.command, self.path, int(self.headers.get("Content-Length") or 0)])
                lock.notify_all()
                return state["root"], state["down"]

        def _answer(self, body: bool) -> None:
            root, down = self._heard()
            if down:
                return self.send_error(503)
            rel = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).lstrip("/") or "index.html"
            file = (root / rel).resolve()
            if not file.is_relative_to(root) or not file.is_file():
                return self._empty(404)
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", types.get(file.suffix.lower(), "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            if pages:
                self.send_header("Cache-Control", "max-age=600")
                self.send_header("Last-Modified", email.utils.formatdate(file.stat().st_mtime, usegmt=True))
            self.end_headers()
            if body:
                self.wfile.write(data)

        def _empty(self, status: int, close: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            if close:   # the request's body, never read, would start the connection's next request
                self.send_header("Connection", "close")
            self.end_headers()

        def do_GET(self) -> None:
            self._answer(True)

        def do_HEAD(self) -> None:
            self._answer(False)

        def _refused(self) -> None:
            self._heard()
            self._empty(405, close=True)

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _refused

    server = Files(("127.0.0.1", 0), Handler)
    print(server.server_port, flush=True)

    def commands() -> None:
        for line in sys.stdin:
            word, _, arg = line.rstrip("\n").partition(" ")
            with lock:
                if word == "root":
                    state["root"] = Path(arg).resolve()
                elif word == "down":
                    state["down"] = arg == "1"
                if word == "heard":
                    seconds, _, path = arg.partition(" ")
                    said = "heard" if lock.wait_for(lambda: any(row[1] == path for row in log), float(seconds)) else \
                        "unheard"
                else:
                    said = json.dumps(log) if word == "log" else "ok" if word in ("root", "down") else f"refused: {word}"
            print(said, flush=True)
        server.shutdown()

    threading.Thread(target=commands, daemon=True).start()
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main(sys.argv)
