"""The one Python client for Ghidra's GhydraMCP HTTP API (stdlib only but
:meth:`GhidraClient.release`), ported from Modkit in Step 4.11d2.

devkit's ``re`` verbs ``ghidra-sync``, ``ghidra-snapshot``,
``ghidra-query``, ``struct-diff`` and ``new-shim --ghidra`` talk to Ghidra
through this module (:func:`connect`).  It speaks the **stock** GhydraMCP
v3.0.0-rc.1 plugin's HTTP API (``uv run bootstrap.py --with re`` installs
it), using stock routes only (checked against the stock plugin on a copy of
the owner's project, AZ-125):

- ``GET  /program``                  — program name + image base
- ``GET  /functions?offset&limit``   — page through every function
- ``GET  /functions/{addr}``         — one function by address
- ``PATCH /functions/{addr}``        — rename
- ``GET  /functions/{addr}/decompile|disassembly`` — one function's C
  text, or its instructions (whose ``bytes`` the client drops, D87)
- ``GET  /xrefs?to_addr&offset&limit`` — references to an address
- ``GET  /memory/{addr}?length&format=hex`` — bytes (only the XBE
  header's, which say the program's release: :meth:`GhidraClient.release`)
- ``GET|POST /memory/{addr}/comments/{kind}`` — read or set a comment
- ``GET  /symbols?offset&limit``     — page through every symbol
- ``GET|POST|PATCH|DELETE /structs…`` — struct layouts

Stock sends names namespace-qualified (``DSOUND::DirectSoundCreate``);
the client hands back bare names, plus the parent namespace for symbols.

Writes go only to a named target (AZ-197): a client built without
``target`` (or with an empty one), or on a port whose ``/program`` serves
another programId (``<project>:<path>``, e.g. ``AzurikServe:/default.xbe``)
or none, refuses every rename, comment and struct write before sending
it, so a forgotten port can't write the owner's project.

The CodeBrowser holding ``default.xbe`` serves on **8193** (Ghidra's
front-end tool takes 8192): that is the one default, and the verbs take
``--port`` to change it.  The host is always ``127.0.0.1``, where
bootstrap binds Ghidra; ``localhost`` would try ``::1`` first (AZ-153).
A client keeps one HTTP/1.1 connection for all its requests, and opens it
again once the server has closed it (AZ-312: a connection per request
churned loopback sockets). Tests run against ``tests/mock_ghidra.py``.

Every method raises :class:`GhidraClientError` on any non-success
response, with the status code and Ghidra's ``error.code`` attached.
"""

from __future__ import annotations

import http.client
import json
import select
import urllib.parse
import weakref
from dataclasses import dataclass
from typing import Iterator

__all__ = [
    "DEFAULT_PORT",
    "GhidraClient",
    "GhidraClientError",
    "GhidraFunction",
    "GhidraLabel",
    "GhidraProgramInfo",
    "GhidraStruct",
    "GhidraStructField",
    "Refused",
    "connect",
    "emit",
    "require_usa",
]

DEFAULT_PORT = 8193  # the CodeBrowser holding default.xbe (the front-end tool takes 8192)


class Refused(Exception):
    """A verb that can't go ahead: its ``main`` prints ``<verb>: <this>`` on
    stderr and exits ``code`` (2: a refusal, nothing written; 1: a failed
    read)."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def connect(port: int | None, *, timeout: float = 10.0,
            target: str | None = None) -> "GhidraClient":
    """How ``ghidra-sync``, ``ghidra-snapshot``, ``ghidra-query`` and
    ``struct-diff`` reach Ghidra: 127.0.0.1 on ``port`` (default 8193, the
    CodeBrowser holding ``default.xbe``). Refuses (exit 2) when nothing
    answers there (``new-shim --ghidra`` builds the same client and carries
    on without ABI pickup instead). Only ``ghidra-sync --target`` makes a
    client that may write."""
    client = GhidraClient(port=port, timeout=timeout, target=target)
    if not client.ping():
        raise Refused(f"no Ghidra instance reachable at {client.base_url}")
    return client


def require_usa(client: "GhidraClient", verb: str) -> None:
    """AZ-326: ``ghidra-sync`` writes USA VAs and ``ghidra-snapshot``
    records the USA program, so both refuse (exit 2), before anything is
    read or written, unless the port serves the USA XBE (its header's
    kernel-thunk address; a Europe RE scratch serve is refused)."""
    try:
        release = client.release()
        what = f"the {release.label} release" if release else "neither Azurik release"
    except GhidraClientError as exc:
        release, what = None, f"a program whose XBE header can't be read ({exc})"
    if release is None or release.name != "usa":
        raise Refused(f"{client.base_url} serves {what}; {verb} works only on the USA "
                      f"default.xbe's program (USA VAs). Nothing written.")


def emit(obj, as_json: bool) -> None:
    """Print ``obj`` as JSON, or as text (a list one item a line)."""
    if as_json:
        print(json.dumps(obj, indent=2))
    elif isinstance(obj, list):
        for item in obj:
            print(item)
    else:
        print(obj)


# ---------------------------------------------------------------------------
# Exceptions + typed responses
# ---------------------------------------------------------------------------


class GhidraClientError(RuntimeError):
    """Any non-success response from the Ghidra HTTP plugin.

    Attributes
    ----------
    status_code: int | None
        HTTP status code (None on connection errors).
    code: str | None
        Ghidra's ``error.code`` value (e.g. ``STRUCT_NOT_FOUND``).
    message: str
        Human-readable error message.
    """

    def __init__(self, *, message: str, status_code: int | None = None,
                 code: str | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(self._format())

    def means_absent(self, code: str) -> bool:
        """Stock's answer for a function or struct that isn't there: a 404
        with ``code`` (``FUNCTION_NOT_FOUND``, ``STRUCT_NOT_FOUND``).  Any
        other error (a lost connection, a timeout) is no answer, so callers
        re-raise it (AZ-202, AZ-232)."""
        return self.status_code == 404 and self.code == code

    def _format(self) -> str:
        bits = [self.message]
        if self.status_code is not None:
            bits.append(f"[HTTP {self.status_code}]")
        if self.code:
            bits.append(f"[{self.code}]")
        return " ".join(bits)


@dataclass(frozen=True)
class GhidraProgramInfo:
    """Result of ``GET /program``.  ``program_id`` is stock's
    ``<project name>:<path in the project>``."""

    name: str
    image_base: int
    program_id: str = ""

    @classmethod
    def from_json(cls, obj: dict) -> "GhidraProgramInfo":
        return cls(name=obj.get("name", ""),
                   image_base=int(obj.get("imageBase", "0"), 16),
                   program_id=obj.get("programId", ""))


@dataclass(frozen=True)
class GhidraFunction:
    """One function entry (``GET /functions`` row or
    ``GET /functions/{addr}``).  ``name`` is bare: function rows carry
    no ``isGlobal``, so it is the last ``::`` part of the stock name."""

    address: int
    name: str
    signature: str | None = None
    parameters: tuple[dict, ...] = ()

    @classmethod
    def from_json(cls, obj: dict) -> "GhidraFunction":
        addr_raw = obj.get("address") or "0"
        return cls(
            address=int(str(addr_raw), 16),
            name=obj.get("name", "").rpartition("::")[2],
            signature=obj.get("signature"),
            parameters=tuple(obj.get("parameters", [])),
        )


@dataclass(frozen=True)
class GhidraLabel:
    """One ``GET /symbols`` row (a label, function or import).

    Stock sends Ghidra's ``getName(true)``: ``a::b::name`` below the
    global namespace, the bare name in it.  Only a global *label* may
    hold ``::`` itself (the string label
    ``s_IDirectSound::GetCaps_failed:_%s_0019ab1c``); a thunk's global
    Function symbol carries its target's path
    (``xboxkrnl.exe::DbgPrint``), so a Function always splits."""

    address: str       # may be "00012345" OR "EXTERNAL:00000001"
    name: str          # bare
    namespace: str     # the parent namespace's name, or "Global"
    symbol_type: str

    @classmethod
    def from_json(cls, obj: dict) -> "GhidraLabel":
        name, symbol_type = obj.get("name", ""), obj.get("type", "")
        if obj.get("isGlobal") and symbol_type != "Function":
            namespace = "Global"
        else:
            path, _, name = name.rpartition("::")
            namespace = path.rpartition("::")[2] or "Global"
        return cls(address=obj.get("address", ""), name=name,
                   namespace=namespace, symbol_type=symbol_type)


@dataclass(frozen=True)
class GhidraStructField:
    """One field inside a :class:`GhidraStruct`."""

    name: str
    data_type: str
    offset: int
    length: int
    comment: str = ""

    @classmethod
    def from_json(cls, obj: dict) -> "GhidraStructField":
        return cls(
            name=obj.get("name", ""),
            data_type=obj.get("type") or "",
            offset=int(obj.get("offset", 0)),
            length=int(obj.get("length", 0)),
            comment=obj.get("comment") or "",
        )


@dataclass(frozen=True)
class GhidraStruct:
    """Result of ``GET /structs/{name}`` — a typed struct layout."""

    name: str
    size: int
    fields: tuple[GhidraStructField, ...]
    category: str = ""
    description: str = ""

    @classmethod
    def from_json(cls, obj: dict) -> "GhidraStruct":
        fields_raw = obj.get("fields") or []
        return cls(
            name=obj.get("name", ""),
            size=int(obj.get("size", 0)),
            fields=tuple(
                GhidraStructField.from_json(f) for f in fields_raw),
            category=obj.get("category", ""),
            description=obj.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass
class _Response:
    """Parsed JSON envelope returned by every Ghidra endpoint."""

    success: bool
    status_code: int
    body: dict


class GhidraClient:
    """Thin HTTP client for the Ghidra instance on ``127.0.0.1:port``.

    Parameters
    ----------
    port: int | None
        HTTP port the plugin listens on; ``None`` means 8193, the
        CodeBrowser holding ``default.xbe`` (the front-end tool takes
        8192).  The verbs' ``--port`` lands here.
    timeout: float
        Per-request timeout in seconds (default 10).
    target: str | None
        The programId writes may go to (``ghidra-sync --target``).
        ``None`` (the default) makes the client read-only: every write
        raises before it is sent (:meth:`check_target`).
    """

    def __init__(self, *, port: int | None = None,
                 timeout: float = 10.0, target: str | None = None) -> None:
        self.port = port or DEFAULT_PORT
        self.timeout = timeout
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.target = target
        self._target_checked = False
        # One connection for the client's life (AZ-312); closed with it.
        self._conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        weakref.finalize(self, self._conn.close)

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, *,
                 params: dict | None = None,
                 json_body: dict | None = None) -> _Response:
        """Low-level HTTP call over the client's one connection (stdlib
        ``http.client``; no third-party deps for the client itself).

        Returns a :class:`_Response` with ``success``, ``status``
        and ``body``; raises :class:`GhidraClientError` on
        connection / timeout issues only — caller decides what to
        do with ``success=False`` bodies.
        """
        target = path
        if params:
            target += "?" + urllib.parse.urlencode(params)
        url = self.base_url + target
        data: bytes | None = None
        headers = {"Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            status, raw = self._exchange(method, target, data, headers)
        except _Unreached as exc:
            raise GhidraClientError(
                message=(f"Failed to reach {url}: {exc.__cause__}"),
                status_code=None,
                code="CONNECTION_ERROR") from exc.__cause__
        except TimeoutError as exc:
            raise GhidraClientError(
                message=f"Request to {url} timed out",
                status_code=None,
                code="REQUEST_TIMEOUT") from exc

        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError as exc:
            raise GhidraClientError(
                message=(f"Non-JSON response from {url}: "
                         f"{raw[:100]!r}"),
                status_code=status,
                code="NON_JSON_RESPONSE") from exc

        success = bool(body.get("success", 200 <= status < 300))
        return _Response(success=success, status_code=status, body=body)

    def _exchange(self, method: str, target: str, data: bytes | None,
                  headers: dict) -> tuple[int, bytes]:
        """``(status, body)`` of one request on the kept-alive connection.

        A failure to connect or send raises :class:`_Unreached`; the
        answer's errors (a read timeout, a malformed answer) pass through,
        as ``urllib``'s did. A reused connection that the server closed
        while it was idle (Ghidra's Jetty does after a while) is opened
        again and the request sent once more when the send fails or the
        connection ends before a byte of answer: the server never read it.
        """
        conn, retried = self._conn, False
        while True:
            reused = conn.sock is not None
            if reused and _readable(conn.sock):  # closed (or talking) before we asked
                conn.close()
                reused = False
            stale = reused and not retried  # a failure now may only mean "closed while idle"
            retried = True
            try:
                conn.request(method, target, body=data, headers=headers)
            except OSError as exc:
                conn.close()
                if stale and not isinstance(exc, TimeoutError):
                    continue
                raise _Unreached from exc
            except BaseException:  # refused before it was sent (an InvalidURL)
                conn.close()  # else the connection stays mid-request
                raise
            try:
                resp = conn.getresponse()
            except ConnectionError:  # closed before a byte of answer (RemoteDisconnected, a reset)
                conn.close()
                if stale:
                    continue
                raise
            except BaseException:
                conn.close()
                raise
            try:
                return resp.status, resp.read()
            except BaseException:
                conn.close()
                raise

    def _require_success(self, resp: _Response) -> dict:
        """Raise :class:`GhidraClientError` on ``success=False``."""
        if resp.success:
            return resp.body
        # The plugin emits ``error`` either as a structured object or
        # as a bare string — accept both.  An unknown route gets
        # Javalin's 404 body instead: no ``error``, the route in ``title``.
        err = resp.body.get("error")
        if isinstance(err, dict):
            message, code = err.get("message"), err.get("code")
        else:
            message, code = (str(err) if err else None), None
        raise GhidraClientError(
            message=(message or resp.body.get("title")
                     or "unknown Ghidra error"),
            status_code=resp.status_code,
            code=code)

    def check_target(self) -> None:
        """Raise :class:`GhidraClientError` (``WRONG_TARGET``) unless
        ``/program`` serves the programId ``target`` names (AZ-197); an
        empty target names nothing, so a port serving no programId never
        matches.  Every write calls it first; one pass lasts the client's
        life."""
        if self._target_checked:
            return
        served = self.program_info().program_id
        if not self.target or served != self.target:
            named = ("no target is named" if self.target is None
                     else f"the target is {self.target!r}")
            raise GhidraClientError(
                message=f"{self.base_url} serves {served!r}, and {named}",
                code="WRONG_TARGET")
        self._target_checked = True

    def _write(self, method: str, path: str, body: dict | None) -> dict:
        """A write request, sent only to the named target."""
        self.check_target()
        return self._require_success(
            self._request(method, path, json_body=body))

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return ``True`` if the server answers ``GET /program``
        with a 2xx; never raises."""
        try:
            self._request("GET", "/program")
            return True
        except GhidraClientError:
            return False

    def program_info(self) -> GhidraProgramInfo:
        """Return the current program's metadata."""
        resp = self._request("GET", "/program")
        body = self._require_success(resp)
        return GhidraProgramInfo.from_json(body.get("result") or {})

    def release(self):
        """The Azurik release (``azurkit.core.gate.Release``) the served
        program is (D146): its XBE header's kernel-thunk address, which
        ghidra-xbe maps at the image base; ``None`` when it is neither
        (AZ-326)."""
        from devkit.re.xbe import release_of
        base = self.program_info().image_base
        header = self._require_success(self._request(
            "GET", f"/memory/{base:08X}", params={"length": 0x15C, "format": "hex"}
            )).get("result") or {}
        try:
            return release_of(bytes.fromhex(header.get("hex") or ""))
        except ValueError:
            return None

    def get_function(self, address: int) -> GhidraFunction:
        """Fetch one function by absolute address."""
        resp = self._request("GET", f"/functions/{address:08X}")
        body = self._require_success(resp)
        return GhidraFunction.from_json(body.get("result") or {})

    def _pages(self, path: str, page_size: int, **params: str) -> Iterator[dict]:
        """Every row of a stock list endpoint (``params`` filter it).
        Stock caps ``limit`` at 1000, so only an empty page ends the list."""
        offset = 0
        while rows := self._require_success(self._request(
                "GET", path, params={**params, "offset": offset, "limit": page_size}
                )).get("result") or []:
            yield from rows
            offset += len(rows)

    def decompile(self, address: int) -> str:
        """The C text of the function that starts at ``address``
        (``FUNCTION_NOT_FOUND`` when none does; ``DECOMPILE_FAILED`` when
        the decompiler gives no code)."""
        result = self._require_success(self._request(
            "GET", f"/functions/{address:08X}/decompile")).get("result") or {}
        if result.get("success") is False or not result.get("decompilation"):
            raise GhidraClientError(
                message=(f"no decompilation of 0x{address:X}: "
                         f"{result.get('errorMessage') or 'empty'}"),
                code="DECOMPILE_FAILED")
        return result["decompilation"]

    def disassemble(self, address: int) -> list[dict]:
        """Every instruction of the function that starts at ``address``,
        as ``address`` (int), ``mnemonic`` and ``operands``; stock's
        ``bytes`` are dropped (D87)."""
        return [{"address": int(row["address"], 16), "mnemonic": row.get("mnemonic", ""),
                 "operands": row.get("operands", "")}
                for row in self._pages(f"/functions/{address:08X}/disassembly", 1000)]

    def xrefs_to(self, address: int) -> list[dict]:
        """Every reference to ``address``: ``from`` (int), ``type``
        (stock's ``refType``, e.g. ``UNCONDITIONAL_CALL``, ``DATA``) and
        ``function``, the function holding it (``""`` outside one)."""
        return [{"from": int(row["fromAddress"], 16), "type": row.get("refType", ""),
                 "function": row.get("fromFunction") or ""}
                for row in self._pages("/xrefs", 1000, to_addr=f"{address:08X}")]

    def iter_functions(self, *, page_size: int = 1000
                       ) -> Iterator[GhidraFunction]:
        """Every function in the program."""
        for row in self._pages("/functions", page_size):
            yield GhidraFunction.from_json(row)

    def rename_function(self, address: int, new_name: str) -> dict:
        """``PATCH /functions/{addr}`` with a new name.

        Returns the raw JSON body on success (contains the updated
        function metadata).
        """
        return self._write("PATCH", f"/functions/{address:08X}",
                           {"name": new_name})

    def get_comment(self, address: int, *, kind: str = "plate") -> str:
        """``GET /memory/{addr}/comments/{kind}``: the comment's text,
        ``""`` when there is none."""
        resp = self._request("GET", _comment_path(address, kind))
        return (self._require_success(resp).get("result") or {}).get(
            "comment") or ""

    def set_comment(self, address: int, comment: str, *,
                    kind: str = "plate") -> dict:
        """``POST /memory/{addr}/comments/{kind}`` with the text.

        ``kind`` is one of ``plate`` / ``pre`` / ``post`` / ``eol``
        / ``repeatable``.  Pass ``comment=""`` to remove an
        existing comment.
        """
        return self._write("POST", _comment_path(address, kind),
                           {"comment": comment})

    def get_struct(self, name: str) -> GhidraStruct:
        """Fetch one struct layout by name.

        Raises :class:`GhidraClientError` (``STRUCT_NOT_FOUND``)
        when the struct isn't defined in the Ghidra project.
        """
        resp = self._request(
            "GET", f"/structs/{name}")
        body = self._require_success(resp)
        return GhidraStruct.from_json(body.get("result") or {})

    def create_struct(self, name: str, *,
                      size: int = 1,
                      description: str = "",
                      ) -> dict:
        """Create a struct of ``size`` undefined bytes in Ghidra's root
        category ``/`` (where ``ghidra-snapshot`` looks for structs);
        :meth:`add_struct_field` then puts each field over the bytes at
        its offset, so the struct keeps this size.

        Raises :class:`GhidraClientError` if Ghidra already has a
        struct with this name (use :meth:`delete_struct` first if
        you want to re-create one from scratch).
        """
        body = {"name": name, "size": int(size)}
        if description:
            body["description"] = description
        return self._write("POST", "/structs", body).get("result") or {}

    def add_struct_field(self, name: str, *, field_name: str,
                         field_type: str,
                         offset: int,
                         comment: str = "",
                         ) -> dict:
        """Put a field over the bytes at ``offset`` of an existing struct
        (``PATCH /structs/{name}/fields/{offset}``); its length is its
        type's and the struct keeps its size.  Stock refuses a field that
        starts inside another or runs into the next defined one or past
        the end.  (Stock *inserts* a field POSTed at an offset, moving
        every later field and growing the struct: AZ-195.)

        Ghidra's field-type names differ from C spelling in a few
        cases (``uint`` / ``ushort`` / ``float`` / ``char`` /
        ``void *`` / etc.).
        """
        body: dict = {"type": field_type, "name": field_name}
        if comment:
            body["comment"] = comment
        return self._write("PATCH", f"/structs/{name}/fields/{int(offset)}",
                           body).get("result") or {}

    def delete_struct(self, name: str) -> None:
        """Remove a struct from the DTM (stock answers 204, no body);
        raises if it didn't exist."""
        self._write("DELETE", f"/structs/{name}", None)

    def iter_structs(self, *, page_size: int = 1000
                     ) -> Iterator[dict]:
        """Every struct in the project, as the list endpoint's raw
        summaries (name / path / size / numFields / category /
        description, no fields) — call :meth:`get_struct` for the
        layout."""
        return self._pages("/structs", page_size)

    def iter_labels(self, *, page_size: int = 1000
                    ) -> Iterator[GhidraLabel]:
        """Every symbol in the program (``GET /symbols``: labels,
        functions and EXTERNAL imports)."""
        for row in self._pages("/symbols", page_size):
            yield GhidraLabel.from_json(row)


class _Unreached(Exception):
    """Connecting or sending failed; its ``__cause__`` says why."""


def _readable(sock) -> bool:
    """Whether an idle kept-alive connection has something to read: the
    server closed it (end of file) or sent what nobody asked for."""
    try:
        return bool(select.select([sock], [], [], 0)[0])
    except (OSError, ValueError):  # ValueError: a descriptor past FD_SETSIZE
        return True


def _comment_path(address: int, kind: str) -> str:
    if kind not in ("plate", "pre", "post", "eol", "repeatable"):
        raise ValueError(f"unsupported comment kind: {kind!r}")
    return f"/memory/{address:08X}/comments/{kind}"
