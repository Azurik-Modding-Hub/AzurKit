"""An in-process stand-in for stock GhydraMCP v3.0.0-rc.1's HTTP API (tests
only; Modkit's, ported in Step 4.11d2).

Serves the stock routes :mod:`devkit.re.ghidra_client` calls, and nothing
else, in stock's response shapes (checked against the stock plugin serving a
copy of the owner's project, AZ-125), over a real socket on an ephemeral port
(or the one given), so devkit's ``ghidra-sync``, ``ghidra-snapshot``,
``ghidra-query``, ``struct-diff`` and ``new-shim --ghidra`` are tested without
a live Ghidra:

- ``GET  /program``
- ``GET  /functions?offset&limit`` · ``GET|PATCH /functions/{addr}``
- ``GET  /functions/{addr}/decompile`` · ``GET /functions/{addr}/disassembly?offset&limit``
- ``GET  /xrefs?to_addr&offset&limit``
- ``GET  /memory/{addr}?length`` (:attr:`MockGhidraServer.header`, at the image base)
- ``GET|POST /memory/{addr}/comments/{type}``
- ``GET  /symbols?offset&limit``
- ``GET|POST /structs`` · ``GET|DELETE /structs/{name}`` ·
  ``PATCH /structs/{name}/fields/{offset}``

As in stock, names go out namespace-qualified (``DSOUND::DirectSoundCreate``;
a name in the global namespace goes out as is, even when it holds ``::``),
list endpoints cap ``limit`` at 1000, and any other route gets Javalin's
404 body. Struct fields behave as stock's do on a serve's copy of the
owner's project (AZ-195): ``POST /structs`` makes ``size`` undefined bytes;
a PATCH at an offset *replaces* the bytes there and keeps the size, refusing
a type name stock doesn't know and a field that starts inside another, runs
into the next defined one or past the end; ``uchar[4]`` is an array of 4
(AZ-200). Unlike stock, undefined bytes are not listed as one-byte
``undefined`` fields. As stock's Javalin does, it answers in HTTP/1.1 and
keeps a connection open for the client's next request (AZ-312: a
connection per request churned loopback sockets); ``connections`` counts
those it accepted, and :meth:`MockGhidraServer.stop` ends any a client
still holds. Mutating endpoints update the state, so a test can probe,
change and re-probe one server::

    with MockGhidraServer() as mock:
        mock.register_function(0x85700, "FUN_00085700")
        GhidraClient(port=mock.port, target="mock:/test.xbe").rename_function(
            0x85700, "gravity")
        assert mock.functions[0x85700].name == "gravity"
"""

from __future__ import annotations

import json
import re
import socket
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


def xbe_header(thunk_va: int) -> bytes:
    """An XBE header holding only its magic and the kernel-thunk address
    ``thunk_va`` (retail-XOR-encoded at 0x158): what tells the releases
    apart."""
    header = bytearray(0x180)
    header[:4] = b"XBEH"
    header[0x158:0x15C] = (thunk_va ^ 0x5B6D40B6).to_bytes(4, "little")
    return bytes(header)


def _qualified(namespace: str, name: str) -> str:
    """Ghidra's ``getName(true)``, which is what stock sends."""
    return name if namespace == "Global" else f"{namespace}::{name}"


@dataclass
class _Function:
    address: int
    name: str
    namespace: str
    signature: str
    parameters: list[dict] = field(default_factory=list)
    decompilation: str = ""
    instructions: list[dict] = field(default_factory=list)

    def to_dict(self, *, detail: bool) -> dict:
        """Stock's ``FunctionDto`` (one function) or ``FunctionSummaryDto``
        (a list row)."""
        row = {"name": _qualified(self.namespace, self.name),
               "address": f"{self.address:08x}", "signature": self.signature,
               "returnType": "undefined", "isExternal": False, "isThunk": False}
        if detail:
            return {**row, "callingConvention": "unknown",
                    "parameters": list(self.parameters), "comment": None}
        return {**row, "parameterCount": len(self.parameters)}


class MockGhidraServer:
    """Threaded HTTP server holding one fake program's state."""

    def __init__(self, port: int = 0) -> None:
        self.host = "127.0.0.1"  # where GhidraClient connects (AZ-153)
        self.port = port  # 0: an ephemeral port, known once started
        self.functions: dict[int, _Function] = {}
        self.symbols: list[dict] = []
        self.comments: dict[tuple[int, str], str] = {}
        self.structs: dict[str, dict] = {}
        self.xrefs: list[dict] = []
        # Some of stock's keys (it also sends path, language, statistics, ...).
        self.program_info: dict[str, Any] = {
            "name": "test.xbe", "programId": "mock:/test.xbe",
            "languageId": "x86:LE:32:default", "compilerSpecId": "windows",
            "imageBase": "00010000",
        }
        # The XBE header ghidra-xbe maps at the image base: its kernel-thunk
        # address says the release (the USA one here; AZ-326).
        self.header = xbe_header(0x18F3A0)
        # (method, path) per request, in order.
        self.request_log: list[tuple[str, str]] = []
        self.connections = 0  # accepted, all told (AZ-312)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- fixtures ---------------------------------------------------------

    def register_function(self, address: int, name: str, *,
                          namespace: str = "Global",
                          signature: str | None = None,
                          parameters: list[dict] | None = None,
                          decompilation: str = "",
                          instructions: list[tuple[int, str, str, str]] = ()) -> None:
        """``parameters`` are stock's ``ParameterDto`` dicts: ``name``,
        ``dataType``, ``ordinal`` and ``storage`` (``ECX:4``,
        ``Stack[0x4]:4``). ``decompilation`` is the C text its decompile
        route sends; ``instructions`` are ``(address, bytes as hex,
        mnemonic, operands)`` rows of its disassembly route."""
        self.functions[address] = _Function(
            address, name, namespace, signature or f"undefined {name}(void)",
            list(parameters or []), decompilation,
            [{"address": f"{a:08x}", "bytes": raw, "mnemonic": m, "operands": ops}
             for a, raw, m, ops in instructions])

    def register_xref(self, from_address: int, to_address: int, ref_type: str,
                      from_function: str | None = None) -> None:
        """One ``GET /xrefs`` row, shaped like stock's ``XrefDto``."""
        self.xrefs.append({
            "fromAddress": f"{from_address:08x}", "toAddress": f"{to_address:08x}",
            "refType": ref_type, "isPrimary": True, "fromFunction": from_function})

    def register_label(self, address: str, name: str, *,
                       namespace: str = "Global",
                       symbol_type: str = "Label") -> None:
        """One ``GET /symbols`` row, shaped like stock's ``SymbolDto``.
        A thunk's Function symbol is global but named after its target:
        pass ``"xboxkrnl.exe::DbgPrint"`` with the default namespace."""
        self.symbols.append({
            "name": _qualified(namespace, name), "address": address,
            "type": symbol_type, "isPrimary": True,
            "isExternal": address.startswith("EXTERNAL:"),
            "isGlobal": namespace == "Global", "source": "USER_DEFINED"})

    def register_struct(self, name: str, *, size: int,
                        fields: list[dict] | None = None,
                        category: str = "/", description: str = "") -> None:
        """Each field dict is stock's ``StructFieldDto``: ``name``,
        ``type``, ``offset``, ``length`` and optionally ``comment``.
        ``/`` is the root category, where ``ghidra-sync`` creates structs."""
        fields = list(fields or [])
        self.structs[name] = {
            "name": name, "path": f"{category.rstrip('/')}/{name}",
            "size": int(size), "numFields": len(fields),
            "category": category, "description": description, "fields": fields,
        }

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        if self._server is None:
            # A thread per connection, so one slow handler never blocks the next.
            self._server = _Server(self, (self.host, self.port), _handler_for(self))
            self.port = self._server.server_address[1]
            # shutdown() waits up to one poll_interval (default 0.5 s).
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                kwargs={"poll_interval": 0.01}, daemon=True,
                name=f"mock-ghidra-{self.port}")
            self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.end_connections()  # else server_close waits on their threads
            self._server.server_close()
            self._thread.join(timeout=2)
            self._server = self._thread = None

    def __enter__(self) -> "MockGhidraServer":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()

    # -- endpoints: each returns (status, result) or raises --------------

    def _route(self, method: str, parts: list[str], query: dict, body: dict):
        match method, parts:
            case "GET", ["program"]:
                return 200, self.program_info
            case "GET", ["functions"]:
                return 200, _page([f.to_dict(detail=False)
                                   for _, f in sorted(self.functions.items())], query)
            case "GET", ["functions", addr]:
                return 200, self._function(addr).to_dict(detail=True)
            case "GET", ["functions", addr, "decompile"]:
                fn = self._function(addr)
                return 200, {"functionName": fn.name, "functionAddress": addr,
                             "decompilation": fn.decompilation, "success": True,
                             "errorMessage": None}
            case "GET", ["functions", addr, "disassembly"]:
                return 200, _page(self._function(addr).instructions, query)
            case "GET", ["xrefs"]:
                to = int(query["to_addr"], 16)
                return 200, _page([x for x in self.xrefs
                                   if int(x["toAddress"], 16) == to], query)
            case "PATCH", ["functions", addr]:
                fn = self._function(addr)
                fn.name = body.get("name") or fn.name  # keeps its namespace
                return 200, fn.to_dict(detail=True)
            case "GET", ["memory", addr]:
                at = int(addr, 16) - int(self.program_info["imageBase"], 16)
                n = int(query.get("length", 16))
                return 200, {"address": addr, "length": n,
                             "hex": self.header[at:at + n].hex() if at >= 0 else ""}
            case "GET", ["memory", addr, "comments", kind]:
                return 200, {"address": addr, "comment_type": kind,
                             "comment": self.comments.get((int(addr, 16), kind), "")}
            case "POST", ["memory", addr, "comments", kind]:
                self.comments[(int(addr, 16), kind)] = body["comment"]
                return 200, {"address": addr, "comment_type": kind,
                             "comment": body["comment"]}
            case "GET", ["symbols"]:
                return 200, _page(self.symbols, query)
            case "GET", ["structs"]:
                return 200, _page([{k: v for k, v in s.items() if k != "fields"}
                                   for s in self.structs.values()], query)
            case "GET", ["structs", name]:
                return 200, self._struct(name)
            case "DELETE", ["structs", name]:
                self._struct(name)
                del self.structs[name]
                return 204, None
            case "POST", ["structs"]:
                self.register_struct(body["name"], size=max(1, body.get("size") or 1),
                                     description=body.get("description") or "")
                return 201, self.structs[body["name"]]
            case "PATCH", ["structs", name, "fields", offset]:  # replaces
                s = self._struct(name)
                fld = _field(body["type"], body["name"], int(offset, 0), body)
                off, fields = fld["offset"], s["fields"]
                if not 0 <= off < s["size"]:
                    raise _Error(500, "INTERNAL_ERROR", "Internal server error: "
                                 "Failed to update field: Operation failed")
                for f in fields:
                    if f["offset"] < off < f["offset"] + f["length"]:
                        raise _Error(400, "BAD_REQUEST", f"fieldOffset {off} is inside "
                                     f"component at offset {f['offset']}; provide the "
                                     "component start offset")
                room = min([f["offset"] for f in fields if f["offset"] > off]
                           + [s["size"]]) - off
                if fld["length"] > room:
                    raise _Error(400, "BAD_REQUEST", f"Field type '{fld['type']}' "
                                 f"({fld['length']} bytes) does not fit at offset {off}; "
                                 f"available bytes before next defined field: {room}")
                s["fields"] = [f for f in fields if f["offset"] != off]
                return 200, _put_field(s, fld)
        raise _NoRoute

    def _function(self, addr: str) -> _Function:
        fn = self.functions.get(int(addr, 16))
        if fn is None:
            raise _Error(404, "FUNCTION_NOT_FOUND", f"No function at address: {addr}")
        return fn

    def _struct(self, name: str) -> dict:
        if name not in self.structs:
            raise _Error(404, "STRUCT_NOT_FOUND", f"Struct not found: {name}")
        return self.structs[name]


class _Server(ThreadingHTTPServer):
    """Counts each connection it accepts in its mock's ``connections``, and
    knows the open ones: a kept-alive connection's thread waits for the
    client's next request until :meth:`end_connections`."""

    def __init__(self, mock: MockGhidraServer, address: tuple[str, int], handler: type) -> None:
        self.mock = mock
        self._open: set[socket.socket] = set()
        self._open_lock = threading.Lock()
        super().__init__(address, handler)

    def process_request(self, request, client_address) -> None:
        self.mock.connections += 1  # serve_forever's one thread
        with self._open_lock:
            self._open.add(request)
        super().process_request(request, client_address)

    def shutdown_request(self, request) -> None:
        with self._open_lock:
            self._open.discard(request)
        super().shutdown_request(request)

    def end_connections(self) -> None:
        """Each open connection's thread reads end-of-file and ends."""
        with self._open_lock:
            requests = list(self._open)
        for request in requests:
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:  # its thread closed it meanwhile
                pass


class _Error(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class _NoRoute(Exception):
    """No stock route matches: Javalin answers, not the plugin."""


# Stock's length for each type name ``ghidra-sync`` sends (AZ-195).
_TYPE_LENGTHS = {"uchar": 1, "char": 1, "byte": 1, "bool": 1, "ushort": 2, "short": 2,
                 "uint": 4, "int": 4, "long": 4, "ulong": 4, "float": 4, "void *": 4,
                 "undefined4": 4, "double": 8, "longlong": 8, "ulonglong": 8}


def _field(ftype: str, name: str, offset: int, body: dict) -> dict:
    """Stock's ``StructFieldDto`` for a field of type ``ftype``; as in
    stock, ``uchar[4]`` is an array of 4 (measured, AZ-200)."""
    base, count = re.fullmatch(r"(.*?)(?:\[(\d+)\])?", ftype).groups()
    if base not in _TYPE_LENGTHS:
        raise _Error(400, "BAD_REQUEST", f"Field type not found: {ftype}")
    return {"name": name, "offset": offset,
            "length": _TYPE_LENGTHS[base] * int(count or 1),
            "type": ftype, "typePath": f"/{ftype}", "comment": body.get("comment") or ""}


def _put_field(struct: dict, fld: dict) -> dict:
    struct["fields"] = sorted([*struct["fields"], fld], key=lambda f: f["offset"])
    struct["numFields"] = len(struct["fields"])
    return struct


def _page(items: list, query: dict) -> list:
    """Stock pagination: ``limit`` defaults to 100 (also for ``limit < 1``)
    and is capped at 1000."""
    offset = max(0, int(query.get("offset", 0)))
    limit = int(query.get("limit", 100))
    limit = 100 if limit < 1 else min(limit, 1000)
    return items[offset:offset + limit]


def _handler_for(server: MockGhidraServer) -> type:
    """A handler class bound to one server: two live servers never share
    state or dispatch."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive: every answer says its length

        def log_message(self, fmt: str, *args: Any) -> None:  # keep pytest output quiet
            return

        def _serve(self, method: str) -> None:
            url = urlparse(self.path)
            server.request_log.append((method, url.path))
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length)) if length else {}
            envelope = {"id": str(uuid.uuid4()),
                        "instance": f"http://{server.host}:{server.port}"}
            try:
                status, result = server._route(method, url.path.strip("/").split("/"), query, body)
                envelope.update(success=True, result=result)
            except _NoRoute:
                status, envelope = 404, {
                    "title": f"Endpoint {method} {url.path} not found", "status": 404,
                    "type": "https://javalin.io/documentation#endpointnotfound",
                    "details": {}}
            except _Error as exc:
                status = exc.status
                envelope.update(success=False, error={"code": exc.code, "message": exc.message})
            except Exception as exc:  # noqa: BLE001 - a handler bug is a 500, never a hang
                status = 500
                envelope.update(success=False, error={"code": "INTERNAL_ERROR",
                                                      "message": f"handler raised: {exc!r}"})
            self.send_response(status)
            if status == 204:  # no body, so no Content-Length (RFC 9110 8.6)
                self.end_headers()
                return
            data = json.dumps(envelope).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 (stdlib contract)
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._serve("POST")

        def do_PATCH(self) -> None:  # noqa: N802
            self._serve("PATCH")

        def do_DELETE(self) -> None:  # noqa: N802
            self._serve("DELETE")

    return Handler
