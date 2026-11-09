"""devkit's Ghidra side (``devkit/re/ghidra_*.py``, ``struct_diff.py``,
``ghidra_scripts/`` and ``bootstrap.py --with re``), Modkit's five Ghidra
test files ported lean in Step 4.11d2, and the Xbox SDK headers' Ghidra copy
(``sdk_headers.py``, Step 4.24c).

The client and the verbs run against ``tests/mock_ghidra.py`` (stock
GhydraMCP's routes and shapes over a real loopback socket; a test that
starts one runs on one worker under ``--dist loadgroup``: AZ-312, a full
run's loopback churn hit an XNU TCP deadlock), ``ghidra-serve`` against a
fake ``analyzeHeadless`` that serves the mock, and ``ghidra-apply`` around
a fake headless run. The tests marked ``ghidra`` run the GhidraScripts in
the real Ghidra that ``uv run bootstrap.py --with re`` installs into
``.tools/`` (a lane uses the main checkout's): without it they fail, naming
it; ``-m "not ghidra"`` deselects them, as CI does. None opens a live
Ghidra or the owner's project.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import io
import json
import os
import re
import shlex
import shutil
import socket
import socketserver
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import bootstrap
from devkit import __main__ as devkit_main
from devkit.re import (
    ghidra_apply, ghidra_project, ghidra_query, ghidra_serve, ghidra_snapshot, ghidra_sync, sdk_headers, struct_diff)
from devkit.re.ghidra_client import GhidraClient, GhidraClientError, GhidraStruct, GhidraStructField, _Response
from devkit.re.ghidra_project import KEEP, ApplyError, LockState, backup, backups, lock_state, manifest, prune, restore
from devkit.re.ghidra_sync import (
    CREATE_FUNCTIONS, _ghidra_type_for, apply_struct_sync, apply_sync, format_plan, plan_struct_sync, plan_sync)
from devkit.re.struct_diff import HeaderField, HeaderStruct, _compare_pair, _normalize_type, diff_structs
from devkit.re.struct_diff import parse_header_structs as parse
from tests.mock_ghidra import MockGhidraServer, xbe_header

ROOT = Path(__file__).resolve().parent.parent
SOCKETS = pytest.mark.xdist_group("ghidra_sockets")
SERVED = "AzurikServe:/default.xbe"
# Holds a project the way Ghidra does: an fcntl write lock on <name>.lock~.
HOLD = """\
import os, sys
fcntl = __import__("fcntl")  # POSIX only: the snippet runs only there
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT)
fcntl.lockf(fd, fcntl.LOCK_EX)
print("held", flush=True)
sys.stdin.read()
"""


def run(capsys, verb, *argv: str) -> tuple[int, str, str]:
    """A verb module's ``main(argv)``: its exit code, stdout and stderr."""
    code = verb.main(list(argv))
    return (code, *capsys.readouterr())


def writes(server: MockGhidraServer) -> list:
    return [r for r in server.request_log if r[0] != "GET"]


def holder(lock: Path) -> subprocess.Popen:
    """A process holding ``lock`` as Ghidra holds ``<name>.lock~``."""
    proc = subprocess.Popen([sys.executable, "-I", "-c", HOLD, str(lock)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True, encoding="utf-8")
    assert proc.stdout.readline() == "held\n"
    return proc


def project(folder: Path) -> Path:
    """A fake ``Azurik Ghidra.gpr`` with a ``.rep`` holding three files."""
    gpr = folder / "Azurik Ghidra.gpr"
    (gpr.with_suffix(".rep") / "idata" / "00").mkdir(parents=True)
    gpr.write_bytes(b"gpr")
    (gpr.with_suffix(".rep") / "project.prp").write_bytes(b"prp")
    (gpr.with_suffix(".rep") / "idata" / "~index.bak").write_bytes(b"bak")
    (gpr.with_suffix(".rep") / "idata" / "00" / "00000000.gbf").write_bytes(b"db")
    return gpr


def hashes(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def sync_mock():
    """The mock serving the USA program, with two functions Ghidra named
    itself and one already named as the facts name it."""
    with MockGhidraServer() as server:
        server.register_function(0x18980, "FUN_00018980", signature="undefined FUN_00018980(void)")
        server.register_function(0x85700, "FUN_00085700", signature="undefined FUN_00085700(undefined *)")
        server.register_function(0x4B510, "entity_lookup", signature="entity_lookup(char *)")
        yield server


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


@SOCKETS
def test_the_client_speaks_stock_ghydras_routes_and_raises_its_errors_typed():
    """Every route the client calls, against the mock: names come back bare,
    a list pages through stock's 1000 cap, a missing function or struct is
    stock's 404 with its code, a route stock lacks is Javalin's 404 body
    (its route in the message), and an envelope with a plain-string error or
    none is still a GhidraClientError (m22). The client's host is the IPv4
    loopback stock Ghydra binds (AZ-153: ``localhost`` tried ::1 first)."""
    assert GhidraClient().base_url == "http://127.0.0.1:8193"
    with MockGhidraServer() as server:
        for i in range(250):
            server.register_function(0x10000 + 16 * i, f"FUN_{0x10000 + 16 * i:08x}")
        server.register_function(0x85700, "gravity_integrate_raw", namespace="PHYS",
                                 signature="undefined gravity(undefined *)")
        server.register_label("00012345", "helper_foo")
        server.register_label("00012400", "helper_bar", namespace="XAPILIB")
        server.register_struct("CritterData", size=272, fields=[
            {"name": "walkSpeed", "type": "float", "offset": 64, "length": 4},
            {"name": "runSpeed", "type": "float", "offset": 68, "length": 4}])
        for i in range(3):
            server.register_struct(f"S{i}", size=8 * (i + 1))
        client = GhidraClient(port=server.port, target="mock:/test.xbe")
        assert client.base_url == f"http://{server.host}:{server.port}"
        assert client.ping() and (client.program_info().name, client.program_info().image_base) == (
            "test.xbe", 0x10000)
        fn = client.get_function(0x85700)
        assert (fn.address, fn.name, fn.signature) == (0x85700, "gravity_integrate_raw", "undefined gravity(undefined *)")
        with pytest.raises(GhidraClientError) as missing:
            client.get_function(0xDEADBEEF)
        assert (missing.value.code, missing.value.status_code) == ("FUNCTION_NOT_FOUND", 404)
        assert len(list(client.iter_functions(page_size=100))) == 251
        assert {(lbl.name, lbl.namespace) for lbl in client.iter_labels()} == {
            ("helper_foo", "Global"), ("helper_bar", "XAPILIB")}
        client.rename_function(0x10000, "gravity")
        client.set_comment(0x10000, "a note", kind="plate")
        assert (server.functions[0x10000].name, server.comments[(0x10000, "plate")]) == ("gravity", "a note")
        with pytest.raises(ValueError, match="unsupported comment kind"):
            client.set_comment(0x10000, "bad", kind="banana")
        critter = client.get_struct("CritterData")
        assert (critter.size, [(f.name, f.offset) for f in critter.fields]) == (
            272, [("walkSpeed", 64), ("runSpeed", 68)])
        assert {s["name"] for s in client.iter_structs(page_size=2)} == {"CritterData", "S0", "S1", "S2"}
        resp = client._request("GET", "/nope")
        with pytest.raises(GhidraClientError, match="GET /nope") as unknown:
            client._require_success(resp)
        assert (resp.success, unknown.value.status_code) == (False, 404)
    for body, message, code in (({"error": "boom, plain string"}, "boom", None),
                                ({}, "unknown Ghidra error", None),
                                ({"error": {"code": "X", "message": "m"}}, "m", "X")):
        with pytest.raises(GhidraClientError, match=message) as err:
            GhidraClient(port=1)._require_success(_Response(success=False, status_code=500, body=body))
        assert err.value.code == code


@SOCKETS
def test_a_client_keeps_one_connection_and_answers_again_after_a_request_it_could_not_send():
    """AZ-312: each request opened its own loopback connection, and a full
    run's churn hit an XNU TCP deadlock that cut the Mac's network until a
    reboot. A client keeps one connection across answers with a body, an
    error or none, opens a new one once the server has closed it, and keeps
    working after a request ``http.client`` refused before sending it (a
    struct name with a space: ``InvalidURL``, which left the connection
    mid-request). Two mocks never share state or dispatch (m23)."""
    with MockGhidraServer() as server:
        for i in range(250):
            server.register_function(0x10000 + 16 * i, f"FUN_{0x10000 + 16 * i:08x}")
        server.register_struct("CritterData", size=4)
        client = GhidraClient(port=server.port, target="mock:/test.xbe")
        assert client.ping()
        assert len(list(client.iter_functions(page_size=100))) == 250
        client.rename_function(0x10000, "gravity")
        client.set_comment(0x10000, "a note")
        assert client.get_struct("CritterData").size == 4
        client.delete_struct("CritterData")  # 204: no body
        with pytest.raises(GhidraClientError, match="STRUCT_NOT_FOUND"):  # 404
            client.get_struct("CritterData")
        assert (len(server.request_log), server.connections) == (11, 1)
        server.register_struct("CritterData", size=4)
        with pytest.raises(http.client.InvalidURL):  # closes the connection it left mid-request
            client.get_struct("Critter Data")
        assert (client.get_struct("CritterData").name, server.connections) == ("CritterData", 2)
        server.program_info["name"] = "SERVER_A"
        with MockGhidraServer() as other:
            other.program_info["name"] = "SERVER_B"
            assert [client.program_info().name, GhidraClient(port=other.port).program_info().name] == [
                "SERVER_A", "SERVER_B"]
    with MockGhidraServer(port=server.port) as again:  # the old connection is closed
        assert (client.program_info().name, again.connections) == ("test.xbe", 1)


# ---------------------------------------------------------------------------
# ghidra-sync, ghidra-query, ghidra-snapshot
# ---------------------------------------------------------------------------


@SOCKETS
def test_ghidra_sync_renames_what_ghidra_named_itself_and_keeps_what_a_user_wrote(sync_mock):
    """The plan renames a function whose Ghidra name differs from the
    facts' and keeps one already named. ``apply`` renames only a name Ghidra
    made up itself (``FUN_``, and AZ-136's ``thunk_FUN_*`` and ``caseD_*``),
    unless ``force``; it writes an empty plate comment, refreshes one
    carrying the sync's marker (Modkit's, so it refreshes Modkit's) and
    keeps a hand-written one unless ``force`` (AZ-194: 20 RE notes on a copy
    of the owner's project were lost), and the dry run names each kept."""
    server = sync_mock
    client = GhidraClient(port=server.port, target="mock:/test.xbe")
    actions = plan_sync(client)
    assert {a.new_name for a in actions if a.kind == "rename"} >= {"play_movie_fn", "gravity_integrate_raw"}
    assert 0x4B510 in {a.va for a in actions if a.kind == "keep"}
    note = "A hand-written RE note."
    server.comments[(0x85700, "plate")] = note
    server.comments[(0x18980, "plate")] = "[azurik_mod.vanilla] play_movie_fn\nAuto-generated by azurik-mod ghidra-sync.\n"
    actions = plan_sync(client)
    planned = {a.va: a.comment for a in actions}
    dry = format_plan(actions).split("=== plate comments")[-1]
    assert "   1 the sync's own: refreshed" in dry
    assert "   1 hand-written: kept (--force replaces them)\n    0x00085700  'FUN_00085700'" in dry
    report = apply_sync(client, actions)
    assert (server.comments[(0x85700, "plate")], server.comments[(0x18980, "plate")],
            server.comments[(0x4B510, "plate")], report.comments_kept) == (
        note, planned[0x18980], planned[0x4B510], 1)
    assert (server.functions[0x18980].name, server.functions[0x85700].name) == (
        "play_movie_fn", "gravity_integrate_raw")
    assert "   1 hand-written: replaced (--force)" in format_plan(actions, force=True)
    apply_sync(client, actions, force=True)
    assert server.comments[(0x85700, "plate")] == planned[0x85700]

    for name, force, after in (("some_cool_custom_name", False, "some_cool_custom_name"),
                               ("some_cool_custom_name", True, "play_movie_fn"),
                               ("thunk_FUN_00018980", False, "play_movie_fn"),
                               ("caseD_3", False, "play_movie_fn")):
        server.register_function(0x18980, name)
        action = next(a for a in plan_sync(client) if a.va == 0x18980)
        report = apply_sync(client, [action], force=force)
        assert (action.kind, report.skipped, server.functions[0x18980].name) == (
            "rename", after == name, after), (name, force)


@SOCKETS
def test_ghidra_sync_and_snapshot_write_only_the_usa_program_the_target_names(sync_mock, tmp_path, capsys):
    """AZ-197: every write went to whatever answered on the port (the
    owner's GUI on 8193). ``ghidra-sync --apply`` exits 2 with nothing
    written unless ``--target`` names the programId served (an empty one
    names nothing, even where none is served), and a client with no target
    writes nothing at all. AZ-326: on a program whose XBE header isn't the
    USA one (a Europe RE serve) both ``ghidra-sync`` and ``ghidra-snapshot``
    exit 2, nothing written. AZ-202: planning stops on a lookup that failed
    other than stock's not-found, instead of planning a rename as a comment
    or an existing struct as a create."""
    server = sync_mock
    argv = ["--apply", "--push-structs", "--port", str(server.port)]
    for program_id, extra in ((SERVED, []), (SERVED, ["--target", "Azurik Ghidra:/default.xbe"]),
                              ("", ["--target", ""])):
        server.program_info.pop("programId", None)
        if program_id:  # else a server that sends no programId
            server.program_info["programId"] = program_id
        code, _, err = run(capsys, ghidra_sync, *argv, *extra)
        assert (code, f"serves {program_id!r}" in err, writes(server)) == (2, True, []), extra
    server.program_info["programId"] = SERVED
    server.register_struct("CritterData", size=4)  # recreated: deleted first
    unnamed = GhidraClient(port=server.port)
    apply_sync(unnamed, plan_sync(unnamed))
    apply_struct_sync(unnamed, plan_struct_sync(unnamed, recreate_existing=True))
    with pytest.raises(GhidraClientError, match="WRONG_TARGET"):
        unnamed.add_struct_field("CritterData", field_name="f", field_type="int", offset=0)
    assert writes(server) == []
    lost = GhidraClientError(message="Failed to reach 127.0.0.1: [Errno 60]", code="CONNECTION_ERROR")
    request = unnamed._request
    with mock.patch.object(unnamed, "_request", side_effect=lambda m, p, **k: (_ for _ in ()).throw(lost)
                           if p.startswith("/functions") else request(m, p, **k)), \
            pytest.raises(GhidraClientError) as stopped:
        plan_sync(unnamed)
    assert stopped.value is lost
    with mock.patch.object(unnamed, "get_struct", side_effect=lost), pytest.raises(GhidraClientError) as stopped:
        plan_struct_sync(unnamed)
    assert stopped.value is lost

    server.header = xbe_header(0x191520)   # Europe's kernel-thunk address
    snap = tmp_path / "snapshot.json"
    for verb, args in ((ghidra_sync, ["--apply", "--target", SERVED]), (ghidra_snapshot, [str(snap)])):
        code, _, err = run(capsys, verb, *args, "--port", str(server.port))
        assert (code, "serves the Europe release" in err) == (2, True), verb
    assert (snap.exists(), writes(server)) == (False, [])
    server.header = xbe_header(0x18F3A0)
    assert run(capsys, ghidra_sync, *argv, "--target", SERVED)[0] == 0
    assert server.functions[0x85700].name == "gravity_integrate_raw"


@SOCKETS
def test_emit_plan_writes_ghidra_apply_lines_for_auto_named_renames_and_listed_creates(sync_mock, tmp_path, capsys):
    """Modkit's Step X.47: ``ghidra-sync --emit-plan FILE`` writes Ghidra
    nothing. Its plan renames only what ``--apply`` would without
    ``--force`` (a name Ghidra made up, never the owner's name at 0x88A80,
    which the facts share since D94), each with the name it expects now,
    then creates each function of the explicit list that no function starts
    at (here all but 0x81240), named when the facts name it (0x42750)."""
    sync_mock.register_function(0x88A80, "player_ground_attack_start")
    sync_mock.register_function(0x81240, "FUN_00081240")
    plan = tmp_path / "plan.json"
    code, out, _ = run(capsys, ghidra_sync, "--emit-plan", str(plan), "--port", str(sync_mock.port))
    lines = json.loads(plan.read_text(encoding="utf-8"))
    assert lines[:2] == [
        {"op": "rename", "va": "0x18980", "from": "FUN_00018980", "to": "play_movie_fn"},
        {"op": "rename", "va": "0x85700", "from": "FUN_00085700", "to": "gravity_integrate_raw"}]
    assert lines[2:] == [{"op": "create_function", "va": "0x42750", "name": "anim_change_at_node"}] + [
        {"op": "create_function", "va": f"0x{va:X}"} for va in CREATE_FUNCTIONS if va not in (0x42750, 0x81240)]
    assert (code, f"2 renames, {len(CREATE_FUNCTIONS) - 1} creates" in out, writes(sync_mock)) == (0, True, [])


@SOCKETS
def test_ghidra_query_reads_a_serve_copy_with_gets_only_and_refuses_any_other_program(capsys):
    """Modkit's Step 2.20g: ``ghidra-query decompile|disasm|xrefs-to VA``
    asks a ``ghidra-serve`` copy and sends only GETs: the function's C text,
    its instructions without their bytes (D87), and each reference to VA
    with its type and function. A VA where no function starts exits 1; a
    port serving any other program (the owner's project) exits 2 having
    asked only for ``/program``."""
    c_text = "void gravity_integrate_raw(void)\n{\n  return;\n}\n"
    with MockGhidraServer() as server:
        server.program_info["programId"] = SERVED
        server.register_function(0x85700, "gravity_integrate_raw", decompilation=c_text,
                                 instructions=[(0x85700, "83ec18", "SUB", "ESP, 0x18"), (0x85703, "c3", "RET", "")])
        server.register_xref(0x89767, 0x85700, "UNCONDITIONAL_CALL", "player_airborne_tick")
        server.register_xref(0x11000, 0x85700, "DATA")
        server.register_xref(0x11004, 0x85704, "DATA", "elsewhere")
        port = ["--port", str(server.port)]
        assert [run(capsys, ghidra_query, action, "0x85700", *port) for action in ("decompile", "disasm", "xrefs-to")] == [
            (0, c_text, ""),
            (0, "0x00085700  SUB ESP, 0x18\n0x00085703  RET\n", ""),
            (0, "0x00089767  UNCONDITIONAL_CALL  in player_airborne_tick\n0x00011000  DATA\n(2 found)\n", "")]
        code, out, _ = run(capsys, ghidra_query, "disasm", "0x85700", "--json", *port)
        assert (code, json.loads(out)[0]) == (0, {"address": 0x85700, "mnemonic": "SUB", "operands": "ESP, 0x18"})
        code, out, err = run(capsys, ghidra_query, "decompile", "0x85705", *port)
        assert (code, out, "FUNCTION_NOT_FOUND" in err) == (1, "", True)
        assert {method for method, _ in server.request_log} == {"GET"}
        server.program_info["programId"] = "Azurik Ghidra:/default.xbe"
        server.request_log.clear()
        code, out, err = run(capsys, ghidra_query, "decompile", "0x85700", *port)
        assert (code, out, "Azurik Ghidra:/default.xbe" in err, {p for _, p in server.request_log}) == (
            2, "", True, {"/program"})


@SOCKETS
def test_the_snapshot_keeps_bare_assigned_names_and_only_the_structs_ghidra_sync_makes(tmp_path):
    """The snapshot drops the names Ghidra made up itself (every automatic
    form it serves for default.xbe: FUN_, thunk_FUN_, caseD_, switchD,
    default, switchdataD_, s_ and u_ string labels with offcut suffixes,
    bare addresses, SUB_, PTR_) unless asked to keep them, keeps stock's
    namespace-qualified names bare with their parent namespace (a global
    label may hold ``::`` itself; a thunk's Function symbol is its target's
    path) and keeps only the structs in the root category ``/``, where
    ``ghidra-sync --push-structs`` makes them (AZ-125)."""
    with MockGhidraServer() as server:
        server.register_function(0x85700, "gravity_integrate_raw")
        server.register_function(0x11390, "FUN_00011390")
        server.register_function(0xAB680, "thunk_FUN_000ab5b0")
        server.register_function(0x30A00, "caseD_8")
        server.register_function(0x1D5A0, "DirectSoundCreate", namespace="DSOUND")
        server.register_label("0018C000", "kernel_thunks")
        for addr, name, ns in [("0002630B", "PTR_caseD_2_00026308+3", "Global"),
                               ("00013490", "caseD_1e", "switchD_00013478"),
                               ("00013478", "switchD", "switchD_00013478"),
                               ("0001349B", "default", "switchD_00013478"),
                               ("0019A000", "switchdataD_0019a000", "Global"),
                               ("0018F7C0", "s_Name_0018f7c0", "Global"),
                               ("0018F7F0", "u_NoCopy=1_0018f7f0", "Global"),
                               ("001A032C", "001a032c", "Global"),
                               ("1E93BCF8", "SUB_1e93bcf8", "Global"),
                               ("0019ab1c", "s_IDirectSound::GetCaps_failed:_%s_0019ab1c", "Global"),
                               ("001a07dd", "s_ICookie/_001a07dc+1", "Global")]:
            server.register_label(addr, name, namespace=ns)
        server.register_label("00187BC0", "g_DeviceType_MU", namespace="XAPILIB")
        server.register_label("EXTERNAL:00000001", "NtClose", namespace="xboxkrnl.exe", symbol_type="Function")
        server.register_label("000f5eb0", "xboxkrnl.exe::DbgPrint", symbol_type="Function")
        server.register_struct("ConfigCell", size=16)
        server.register_struct("AzurikSmokeTestProbe", size=8, category="/AzurikSmokeTest/ghydra-header-1.h")
        client = GhidraClient(port=server.port)
        snap, stats = ghidra_snapshot.dump_snapshot(client)
        assert snap["program"] == {"name": "test.xbe", "image_base": "0x00010000"}
        assert snap["functions"] == [{"address": "0x0001D5A0", "name": "DirectSoundCreate"},
                                     {"address": "0x00085700", "name": "gravity_integrate_raw"}]
        assert snap["labels"] == [
            {"address": "0018C000", "name": "kernel_thunks", "namespace": "Global", "type": "Label"},
            {"address": "00187BC0", "name": "g_DeviceType_MU", "namespace": "XAPILIB", "type": "Label"},
            {"address": "EXTERNAL:00000001", "name": "NtClose", "namespace": "xboxkrnl.exe", "type": "Function"},
            {"address": "000f5eb0", "name": "DbgPrint", "namespace": "xboxkrnl.exe", "type": "Function"}]
        assert ([s["name"] for s in snap["structs"]], stats.named_functions, stats.total_functions) == (
            ["ConfigCell"], 2, 5)
        assert "FUN_00011390" in {f["name"] for f in ghidra_snapshot.dump_snapshot(
            client, include_default_names=True)[0]["functions"]}
        assert ghidra_snapshot.dump_snapshot(client, include_labels=False)[0]["labels"] == []
        ghidra_snapshot.write_snapshot(tmp_path / "s.json", client)
        assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["schema"] == 1


# ---------------------------------------------------------------------------
# Structs: the push and struct-diff
# ---------------------------------------------------------------------------

TINY = """
typedef struct TinyHeaderStruct {
    u32 first;         /* +0x00 */
    u32 second;        /* +0x04 */
    u16 third;         /* +0x08 */
    u8  fourth;        /* +0x0A */
} TinyHeaderStruct;

typedef struct FloatyStruct {
    f32 x;             /* +0x00 */
    f32 y;             /* +0x04 */
    char *name;        /* +0x08 */
} FloatyStruct;
"""
FOO_BAR = """
typedef struct Foo {
    u32 a;         /* +0x00 first */
    u32 b;         /* +0x04 second */
} Foo;

typedef struct Bar {
    float x;       /* +0x00 */
    float y;       /* +0x04 */
    float z;       /* +0x08 */
} Bar;

_Static_assert(sizeof(Foo) == 8, "Foo size wrong");
"""


@SOCKETS
def test_a_struct_push_makes_header_sized_typed_structs_that_struct_diff_finds_equal(tmp_path):
    """``--push-structs`` plans a create for each header struct Ghidra
    hasn't got and keeps one it has unless ``--recreate-structs``, which
    deletes it first; it makes each struct the header's size and puts each
    field over the bytes at its offset as Ghidra's type (a pointer
    ``void *``, an unknown ``undefined4``, an array of its element: AZ-200),
    since stock *inserts* a field POSTed at an offset and grew ConfigCell
    16 -> 32 (AZ-195). Pushing structs.h whole, struct-diff then finds no
    mismatch (AZ-233: gap arrays and function pointers were pushed empty)."""
    assert [_ghidra_type_for(t) for t in ("u32", "s32", "u16", "f32", "u8", "char *", "const char *", "int *",
                                          "MyCustomType", "u8[12]")] == [
        "uint", "int", "ushort", "float", "uchar", "void *", "void *", "void *", "undefined4", "uchar[12]"]
    tiny = tmp_path / "tiny.h"
    tiny.write_text(TINY, encoding="utf-8")
    padded = tmp_path / "padded.h"
    padded.write_text("""
typedef struct PaddedStruct {
    u32 kind;          /* +0x00 */
    u16 flags;         /* +0x04 */
    f64 value;         /* +0x08 */
    u8  edge;          /* +0x10 */
} PaddedStruct;
_Static_assert(sizeof(PaddedStruct) == 0x18, "PaddedStruct size");

typedef struct WithArrays {
    char fourcc[4];    /* +0x00 */
    u8   edge[12];     /* +0x04 */
} WithArrays;
_Static_assert(sizeof(WithArrays) == 0x10, "WithArrays size");
""", encoding="utf-8")
    with MockGhidraServer() as server:
        client = GhidraClient(port=server.port, target="mock:/test.xbe")
        server.register_struct("TinyHeaderStruct", size=99)
        kinds = {a.name: a.kind for a in plan_struct_sync(client, header=tiny)}
        assert kinds == {"TinyHeaderStruct": "keep", "FloatyStruct": "create"}
        report = apply_struct_sync(client, plan_struct_sync(client, header=tiny), header=tiny)
        assert (report.structs_created, report.structs_skipped, client.get_struct("TinyHeaderStruct").size) == (
            1, 1, 99)
        actions = plan_struct_sync(client, header=tiny, recreate_existing=True)
        assert {a.name: a.kind for a in actions} == {"TinyHeaderStruct": "recreate", "FloatyStruct": "recreate"}
        report = apply_struct_sync(client, actions, header=tiny)
        assert (report.structs_created, report.struct_fields_added, report.errors) == (2, 7, [])
        assert [(f.name, f.data_type) for f in client.get_struct("TinyHeaderStruct").fields] == [
            ("first", "uint"), ("second", "uint"), ("third", "ushort"), ("fourth", "uchar")]
        again = apply_struct_sync(client, plan_struct_sync(client, header=tiny), header=tiny)
        assert (again.structs_created, again.structs_skipped, again.errors) == (0, 2, [])

        assert apply_struct_sync(client, plan_struct_sync(client, header=padded), header=padded).errors == []
        assert [(e.name, e.status, e.ghidra_size, e.notes) for e in diff_structs(
            header=padded, client=client).entries if e.name in ("PaddedStruct", "WithArrays")] == [
            ("PaddedStruct", "ok", 0x18, ()), ("WithArrays", "ok", 0x10, ())]
        assert [(f.name, f.data_type, f.offset, f.length) for f in client.get_struct("WithArrays").fields] == [
            ("fourcc", "char[4]", 0, 4), ("edge", "uchar[12]", 4, 12)]

    with MockGhidraServer() as server:
        client = GhidraClient(port=server.port, target="mock:/test.xbe")
        assert apply_struct_sync(client, plan_struct_sync(client)).errors == []
        assert [(e.name, e.status, e.notes) for e in diff_structs(header=struct_diff.HEADER, client=client).entries
                if e.status != "ok"] == []
        assert [(f.name, f.data_type, f.offset) for f in client.get_struct("MovieContextVTable").fields] == [
            ("advance", "void *", 0x0), ("is_done", "void *", 0x4), ("_reserved_08", "void *", 0x8),
            ("_reserved_0C", "void *", 0xC), ("destroy", "void *", 0x10)]


def test_the_header_parser_and_struct_diff_read_offsets_arrays_and_sizes_but_never_a_comment():
    """The parser reads each ``typedef struct`` block's fields from their
    ``/* +0xHH */`` offsets and a ``_Static_assert`` size; a comment is never
    a declaration (AZ-198: "a negative HP; live HP is critter+0x210" became
    a field); a struct ending in a wide int or an array infers its full size
    (AZ-199). struct-diff tells ok from a size or field mismatch, matches
    the ``i`` typedefs and arrays to Ghidra's names (AZ-200), and a Ghidra
    field with no data type is a mismatch, not a crash (m24)."""
    foo, bar = sorted(parse(FOO_BAR), key=lambda s: s.name != "Foo")
    assert (foo.declared_size, [(f.name, f.offset) for f in foo.fields], bar.inferred_size()) == (
        8, [("a", 0), ("b", 4)], 12)
    floats = tuple(GhidraStructField(n, "float", o, 4) for n, o in (("x", 0), ("y", 4), ("z", 8), ("w", 12)))
    report = diff_structs(header=[foo, bar], ghidra_structs=[
        GhidraStruct("Foo", 8, (GhidraStructField("a", "uint", 0, 4), GhidraStructField("b", "int", 4, 4))),
        GhidraStruct("Bar", 16, floats), GhidraStruct("Baz", 4, ())])
    assert [(e.name, e.status) for e in report.entries] == [
        ("Bar", "size_mismatch"), ("Baz", "ghidra_only"), ("Foo", "field_mismatch")]
    assert report.counts() | {} == {"header_only": 0, "ghidra_only": 1, "size_mismatch": 1,
                                    "field_mismatch": 1, "ok": 0}

    (commented,) = parse("""
typedef struct Commented {
    u32 a;             /* +0x00 */
    /* A note on b, x; y +0x10
     * a negative HP; live HP is critter+0x210 */
    u32 b;             /* +0x04 x; y +0x10 */
                       /* z; w +0x20 */
} Commented;
""")
    assert ([(f.name, f.offset) for f in commented.fields], commented.inferred_size()) == ([("a", 0), ("b", 4)], 8)
    assert {s.name: s.inferred_size() for s in parse("""
typedef struct EndsInI64 {
    u32 a;             /* +0x00 */
    i64 big;           /* +0x08 */
} EndsInI64;

typedef struct EndsInArray {
    u32 a;             /* +0x00 */
    u8  x[12];         /* +0x04 */
} EndsInArray;

typedef struct EndsInGap {
    u32 a;             /* +0x00 */
    u8  _reserved_04[0x10 - 0x04];  /* +0x04 */
} EndsInGap;
""")} == {"EndsInI64": 16, "EndsInArray": 16, "EndsInGap": 16}
    signed = parse("""
typedef struct Signed {
    i8  a;             /* +0x00 */
    i16 b;             /* +0x02 */
    i32 c;             /* +0x04 */
    i64 d;             /* +0x08 */
    u8  e[4];          /* +0x10 */
} Signed;
_Static_assert(sizeof(Signed) == 20, "Signed size");
""")
    ghidra = GhidraStruct("Signed", 20, (GhidraStructField("a", "char", 0, 1), GhidraStructField("b", "short", 2, 2),
                                         GhidraStructField("c", "int", 4, 4), GhidraStructField("d", "longlong", 8, 8),
                                         GhidraStructField("e", "uchar[4]", 16, 4)))
    (entry,) = diff_structs(header=signed, ghidra_structs=[ghidra]).entries
    assert (entry.status, entry.notes) == ("ok", ())
    assert (_normalize_type(""), _normalize_type("   ")) == ("", "")
    untyped = GhidraStruct.from_json({"name": "S", "size": 4, "fields": [{"name": "a", "offset": 0, "length": 4}]})
    assert _compare_pair(HeaderStruct("S", (HeaderField("a", "int", 0),), 4), untyped).status == "field_mismatch"


def test_struct_diff_stops_when_ghidra_fails_the_listing_or_a_lookup(tmp_path, capsys):
    """AZ-232 and AZ-251: struct-diff read any error from a struct lookup or
    a failed listing page as "not there", reporting every header struct
    ``header_only`` and exiting 0. Only stock's 404 ``STRUCT_NOT_FOUND`` (a
    struct gone since the listing) means absent; any other error exits 1,
    the error on stderr and nothing on stdout. ``--offline`` reads the
    header alone."""
    header = tmp_path / "structs.h"
    header.write_text(FOO_BAR, encoding="utf-8")
    lost = GhidraClientError(message="Failed to reach 127.0.0.1: [Errno 60]", code="CONNECTION_ERROR")
    client = mock.create_autospec(GhidraClient, instance=True)
    client.iter_structs.side_effect = lambda: iter([{"name": "Foo"}])
    client.get_struct.side_effect = GhidraClientError(message="Struct not found: Foo", status_code=404,
                                                      code="STRUCT_NOT_FOUND")
    assert [(e.name, e.status) for e in diff_structs(header=header, client=client).entries] == [
        ("Bar", "header_only"), ("Foo", "header_only")]

    def pages():  # page 1 answers, page 2 is lost
        yield {"name": "Foo"}
        raise lost

    for listing, lookup in ((lambda: iter([{"name": "Foo"}]), lost), (pages, None)):
        client.iter_structs.side_effect, client.get_struct.side_effect = listing, lookup
        with mock.patch.object(struct_diff, "connect", return_value=client):
            assert run(capsys, struct_diff, "--header", str(header)) == (1, "", f"struct-diff: {lost}\n")
    code, out, _ = run(capsys, struct_diff, "--header", str(header), "--offline")
    assert (code, "header_only=2" in out) == (0, True)


# ---------------------------------------------------------------------------
# The project on disk and ghidra-apply's backups
# ---------------------------------------------------------------------------


def test_the_lock_probe_tells_a_held_project_from_a_free_or_stale_one(tmp_path):
    """The passive probe answers free with no lock files, held with the
    holder's PID while a process holds ``<name>.lock~``, and stale once that
    process is gone; it creates nothing. Windows has no passive probe:
    "unknown"."""
    gpr = tmp_path / "Azurik Ghidra.gpr"
    lock = gpr.with_suffix(".lock")
    assert (lock_state(gpr), list(tmp_path.iterdir())) == (LockState("free"), [])
    lock.write_text("Lock type=channel\n", encoding="utf-8")
    if os.name == "nt":
        assert lock_state(gpr) == LockState("unknown")
        return
    with holder(Path(f"{lock}~")) as held:
        assert lock_state(gpr) == LockState("held", held.pid)
        held.stdin.close()
        held.wait(timeout=30)
    assert lock_state(gpr) == LockState("stale")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Azurik Ghidra.lock", "Azurik Ghidra.lock~"]


def test_backup_restore_and_prune_keep_the_project_byte_identical(tmp_path):
    """Q205: a backup is a copy with a sha256 manifest, in ghidra-backups/
    beside the project's folder. A restore puts it back byte-identical and
    moves the project it replaces aside (never deleting it); it refuses a
    backup that no longer matches its manifest. Prune keeps the newest
    ``KEEP`` backups of the project and touches nothing else, not even a
    backup of a project of the same name in a folder beside it."""
    gpr = project(tmp_path / "ghidra")
    before = hashes(gpr.parent)
    saved = backup(gpr)
    assert saved.parent == tmp_path / "ghidra-backups"
    assert json.loads((saved / "manifest.json").read_text(encoding="utf-8"))["files"] == manifest(gpr) == manifest(
        saved / gpr.name)
    (gpr.with_suffix(".rep") / "idata" / "00" / "00000000.gbf").write_bytes(b"db, saved later")
    (gpr.with_suffix(".rep") / "idata" / "00" / "00000001.gbf").write_bytes(b"new")
    later = hashes(gpr.parent)
    aside = restore(gpr, saved)
    assert hashes(gpr.parent) == before
    assert {k: v for k, v in hashes(aside).items() if k != "manifest.json"} == later
    (saved / gpr.with_suffix(".rep").name / "project.prp").write_bytes(b"torn")
    with pytest.raises(ApplyError, match="no longer matches its manifest"):
        restore(gpr, saved)
    assert hashes(gpr.parent) == before
    (tmp_path / "ghidra-backups" / "notes").mkdir()
    other = backup(project(tmp_path / "ghidra-old"))
    for _ in range(2):
        backup(gpr)
    names = [d.name for d, _ in backups(gpr)]
    assert len(names) == 4
    assert [d.name for d in prune(gpr)] == names[:-KEEP]
    assert [d.name for d, _ in backups(gpr)] == names[-KEEP:]
    assert (tmp_path / "ghidra-backups" / "notes").is_dir() and other.is_dir()


def fake_ghidra(apply, verify="AZVERIFY: OK 1 lines in effect"):
    """Stands in for analyzeHeadless running ApplyPlan.java, which always
    exits 0: an apply run saves the project (a database file changes, as
    every writable run does) and prints ``apply``; a dry or verify run
    prints its marker; a mode given an exception raises it (a run that
    timed out). ``seen`` records (mode, the project it opened)."""
    def runner(gpr, mode, plan):
        runner.seen.append((mode, gpr))
        final = {"apply": apply, "verify": verify, "dry": "AZPLAN: DRY 1 of 1 pending"}[mode]
        if isinstance(final, Exception):
            raise final
        out = ['INFO  ApplyPlan.java> AZPLAN: pending comment 00000000 plate "AZPLAN: APPLIED 1 of 1" '
               "(none before) (GhidraScript)  ", f"INFO  ApplyPlan.java> {final} (GhidraScript)  "]
        if final == "AZPLAN: ROLLED BACK":
            out.append("ERROR REPORT SCRIPT ERROR:  (HeadlessAnalyzer) java.lang.IllegalStateException: "
                       "plan line 1 is not in effect after the apply")
        if mode == "apply":
            db = gpr.with_suffix(".rep") / "idata" / "00" / "00000000.gbf"
            db.write_bytes(db.read_bytes() + b" saved")
            out.append("INFO  REPORT: Save succeeded for processed file: /default.xbe (HeadlessAnalyzer)  ")
        return "\n".join(out) + "\n"
    runner.seen = []
    return runner


def plan_file(tmp_path: Path, line: dict | None = None) -> tuple[Path, str]:
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps([line or {"op": "delete_equate", "name": "AZURIK_SMOKETEST_ONE"}]), encoding="utf-8")
    return plan, ghidra_apply.plan_sha256(plan)


def test_apply_refuses_an_unapproved_plan_an_unnamed_or_held_project_or_no_ghidra_before_any_backup(
        tmp_path, monkeypatch, capsys):
    """D90: ``ghidra-apply --apply`` writes only the plan whose sha256 its
    dry run printed (D103), only into the project its ``--project`` names
    (never the one ``ghidra-serve`` last used: any lane's start rewrites
    that; the dry run's command names the project it read), only with a
    Ghidra it can run, and only to a project no Ghidra holds (the lock
    probe; on Windows, any lock file). Each refusal comes before the
    backup: no folder, no run, the project untouched."""
    gpr = project(tmp_path / "ghidra")
    plan, sha = plan_file(tmp_path)
    before, work = hashes(gpr.parent), tmp_path / "work"
    runner = fake_ghidra("AZPLAN: APPLIED 1 of 1")
    with pytest.raises(ApplyError, match=f"sha256 is {sha}, not the approved"):
        ghidra_apply.apply_plan(gpr, plan, hashlib.sha256(b"another plan").hexdigest(), runner=runner,
                                work_root=work)
    monkeypatch.setattr(ghidra_serve, "tools_dir", lambda: tmp_path / "no-tools")
    with pytest.raises(ApplyError, match="analyzeHeadless"):
        ghidra_apply.apply_plan(gpr, plan, sha, work_root=work)
    monkeypatch.setattr(ghidra_serve, "remembered_project", lambda: gpr)
    monkeypatch.setattr(ghidra_apply, "_headless", lambda program, work: runner)  # were it reached
    code, _, err = run(capsys, ghidra_apply, "--plan", str(plan), "--apply", "--plan-sha256", sha)
    assert (code, "name the project" in err) == (2, True)
    lock = gpr.with_suffix(".lock")
    lock.write_text("Lock type=channel\n", encoding="utf-8")
    if os.name == "nt":
        with pytest.raises(ApplyError, match="no passive lock probe"):
            ghidra_apply.apply_plan(gpr, plan, sha, runner=runner, work_root=work)
    else:
        with holder(Path(f"{lock}~")) as held:
            with pytest.raises(ApplyError, match=f"a Ghidra holds .*pid {held.pid}"):
                ghidra_apply.apply_plan(gpr, plan, sha, runner=runner, work_root=work)
            held.stdin.close()
    assert (runner.seen, (tmp_path / "ghidra-backups").exists()) == ([], False)
    lock.unlink()
    Path(f"{lock}~").unlink(missing_ok=True)
    assert hashes(gpr.parent) == before
    monkeypatch.setattr(ghidra_serve, "state_root", lambda: tmp_path / "state")  # its work folder
    code, out, _ = run(capsys, ghidra_apply, "--plan", str(plan))
    assert (code, f"--project {shlex.quote(str(gpr))}" in out) == (0, True)


def test_apply_writes_a_verified_plan_keeps_one_undo_and_puts_a_failed_one_back_byte_identical(
        tmp_path, monkeypatch, capsys):
    """The dry run reads a copy and prints the plan's sha256. An apply backs
    the project up, runs the plan on it and verifies on a copy of the
    result; the logs, the plan and the result stay with the backup, which
    the prune after it keeps whatever the clock said. Success is read from
    the markers, never the exit code: a run that rolled back (a script
    error, exit 0), a failed verify or one that timed out puts the backup
    back and keeps the project the run left aside. D103: a verified apply
    keeps only its own backup; a failed one deletes none, so the last
    verified apply's undo survives it. AZ-242: the undo command a verified
    apply prints, run as printed, puts the project back byte-identical."""
    gpr = project(tmp_path / "Ghidra projects")
    for n in range(KEEP):  # backups named by a clock ahead of this one
        os.rename(backup(gpr), tmp_path / "ghidra-backups" / f"2099010{n}T000000Z")
    work = tmp_path / "work"
    plan, sha = plan_file(tmp_path, {"op": "comment", "va": "0x0", "kind": "plate", "text": "AZPLAN: APPLIED 1 of 1"})
    before = manifest(gpr)
    ok = fake_ghidra("AZPLAN: APPLIED 1 of 1")
    dry = ghidra_apply.dry_run(gpr, plan, runner=ok, work_root=work)
    assert (dry["plan_sha256"], dry["lines"][-1], dry["lock"], manifest(gpr)) == (
        sha, "AZPLAN: DRY 1 of 1 pending", LockState("free"), before)
    first = ghidra_apply.apply_plan(gpr, plan, sha.upper(), runner=ok, work_root=work)
    assert (first["applied"], first["verified"], first["restored"]) == (True, True, False)
    saved = Path(first["backup"])
    assert manifest(saved / gpr.name) == before != manifest(gpr)
    assert sorted(p.name for p in saved.iterdir()) == [
        gpr.name, gpr.with_suffix(".rep").name, "apply.log", "manifest.json", "plan.json", "result.json",
        "verify.log"]
    assert [(mode, opened == gpr) for mode, opened in ok.seen] == [("dry", False), ("apply", True),
                                                                    ("verify", False)]
    timed_out = ApplyError("analyzeHeadless (verify) ran over 600 s")
    for failing in (fake_ghidra("AZPLAN: ROLLED BACK"),
                    fake_ghidra("AZPLAN: APPLIED 1 of 1", verify="AZVERIFY: FAIL 1 of 1 lines not in effect"),
                    fake_ghidra("AZPLAN: APPLIED 1 of 1", verify=timed_out)):
        state, files = hashes(gpr.parent), manifest(gpr)
        r = ghidra_apply.apply_plan(gpr, plan, sha, runner=failing, work_root=work)
        assert (r["verified"], r["restored"], r["pruned"], hashes(gpr.parent)) == (False, True, [], state), r
        assert manifest(Path(r["replaced"]) / gpr.name) != files
        assert json.loads((Path(r["backup"]) / "result.json").read_text(encoding="utf-8"))["why"] == r["why"]
    assert list(work.iterdir()) == []
    assert Path(first["backup"]) in [d for d, _ in backups(gpr)]
    assert Path(first["backup"]) not in prune(gpr)
    monkeypatch.setattr(ghidra_apply, "_headless", lambda program, work: fake_ghidra("AZPLAN: APPLIED 1 of 1"))
    monkeypatch.setattr(ghidra_serve, "state_root", lambda: tmp_path / "state")  # its work folder
    before = hashes(gpr.parent)
    code, out, _ = run(capsys, ghidra_apply, "--plan", str(plan), "--apply", "--plan-sha256", sha,
                       "--project", str(gpr))
    assert (code, hashes(gpr.parent) != before) == (0, True)
    assert [d.name for d, _ in backups(gpr)] == [Path(out.split("backup: ")[1].split(" (")[0]).name] + [
        f"2099010{n}T000000Z" for n in range(KEEP)]   # its own and the newest KEEP
    undo = shlex.split(out.split("(to undo: ", 1)[1].rsplit(")", 1)[0])
    assert undo[:4] == ["python", "-m", "devkit", "re"] and devkit_main.main(undo[3:]) == 0
    assert hashes(gpr.parent) == before


# Stands in for the JVM, which runs under analyzeHeadless and launch.sh: it
# writes the project's database over and over, as a long save would.
WRITER = """\
import pathlib, sys, time
pathlib.Path(__file__).with_name("started").touch()
db = pathlib.Path(sys.argv[1], sys.argv[2] + ".rep", "idata", "00", "00000000.gbf")
for _ in range(200):
    try:
        with open(db, "ab") as f:
            f.write(b"x")
    except OSError:  # a restore has the project aside for a moment
        pass
    time.sleep(0.05)
"""


def test_an_apply_ends_its_whole_ghidra_and_never_restores_under_one_that_holds_the_project(tmp_path, monkeypatch):
    """A timeout (or Ctrl-C) that killed only analyzeHeadless would leave
    the JVM under it writing the project after the verb returned. The run
    is a process group of its own, ended whole, so the backup goes back and
    nothing writes the project after the apply has returned. A Ghidra still
    holding the project once the run is over (one that outlived its kill,
    or one opened since) may still write: then nothing is put back nor
    called unchanged, and ``restore_failed`` says why."""
    gpr = project(tmp_path / "ghidra")
    support = tmp_path / "tools" / "ghidra" / "support"
    support.mkdir(parents=True)
    (support / "writer.py").write_text(WRITER, encoding="utf-8")
    call = f'"{sys.executable}" -I "{support / "writer.py"}"'
    if os.name == "nt":
        (support / "analyzeHeadless.bat").write_text(f"@{call} %*\n", encoding="utf-8")
    else:
        (support / "analyzeHeadless").write_text(f'#!/bin/sh\n{call} "$@"\n', encoding="utf-8")
        (support / "analyzeHeadless").chmod(0o755)
    monkeypatch.setattr(ghidra_serve, "tools_dir", lambda: tmp_path / "tools")
    monkeypatch.setattr(ghidra_apply, "_TIMEOUT", 2)
    plan, sha = plan_file(tmp_path)
    before = manifest(gpr)
    r = ghidra_apply.apply_plan(gpr, plan, sha, work_root=tmp_path / "work")
    assert ((support / "started").exists(), r["why"], r["restored"]) == (
        True, "analyzeHeadless (apply) ran over 2 s", True), r
    time.sleep(0.5)
    assert manifest(gpr) == before

    lock, holders = gpr.with_suffix(".lock"), []

    def outlived(project, mode, plan):
        lock.write_text("Lock type=channel\n", encoding="utf-8")
        if os.name != "nt":
            holders.append(holder(Path(f"{lock}~")))
        return "INFO  ApplyPlan.java> AZPLAN: ROLLED BACK (GhidraScript)\n"

    try:
        r = ghidra_apply.apply_plan(gpr, plan, sha, runner=outlived, work_root=tmp_path / "work")
    finally:
        for held in holders:
            with held:
                held.stdin.close()
    assert (r["restored"], "restore_failed" in r) == (False, True), r


# ---------------------------------------------------------------------------
# ghidra-serve, on a fake analyzeHeadless serving the mock
# ---------------------------------------------------------------------------

# Records how it was started, serves the mock on the post-script's port and
# writes its ready file, until the stop file.
FAKE_HEADLESS = """\
import json, os, sys, time
sys.path.insert(0, {repo!r})
from tests.mock_ghidra import MockGhidraServer
argv = sys.argv[1:]
port, stop, ready, _ = argv[argv.index("AzurikServe.java") + 1:][:4]
with open({record!r}, "w", encoding="utf-8") as f:
    json.dump({{"argv": argv, "options": os.environ["GHIDRA_HEADLESS_JAVA_OPTIONS"],
               "bind": os.environ.get("GHYDRA_BIND_HOST")}}, f)
with MockGhidraServer(port=int(port)) as mock:
    mock.program_info["programId"] = "AzurikServe:/default.xbe"
    with open(ready, "w", encoding="utf-8") as f:
        json.dump({{"readyModificationNumber": 7, "modificationNumber": 7}}, f)
    while not os.path.exists(stop):
        time.sleep(0.05)
"""


@pytest.fixture
def serve(tmp_path, monkeypatch):
    """The fake serve of a fake project on a free port, its state in
    ``tmp_path``; stopped at teardown if the test didn't stop it."""
    gpr = project(tmp_path / "src")
    root = tmp_path / "state"
    monkeypatch.setattr(ghidra_serve, "state_root", lambda: root)
    fake, record = tmp_path / "fake_headless.py", tmp_path / "fake_run.json"
    fake.write_text(FAKE_HEADLESS.format(repo=str(ROOT), record=str(record)), encoding="utf-8")
    headless, port = [sys.executable, "-I", str(fake)], free_port()
    served = ghidra_serve.start(gpr, port, root=root, headless=headless, timeout=60)
    yield SimpleNamespace(gpr=gpr, root=root, port=port, headless=headless, record=record,
                          proc=ghidra_serve._CHILDREN[served["pid"]])
    ghidra_serve.stop(port, root, timeout=30)


def test_serves_and_apply_work_outside_a_hidden_user_cache_ghidra_would_refuse(tmp_path, monkeypatch):
    """Ghidra refuses a project under a folder whose name starts with ``.``:
    under Linux's hidden ``~/.cache`` the serves' state and ghidra-apply's
    work go to the main checkout's ``out/``, as Modkit's did; a user cache
    that isn't hidden (macOS's, Windows') keeps them."""
    import platformdirs
    monkeypatch.setattr(ghidra_serve, "_main_checkout", lambda: tmp_path / "main")
    for cache, root in ((tmp_path / "home" / ".cache" / "AzurKit", tmp_path / "main" / "out"),
                        (tmp_path / "Caches" / "AzurKit", tmp_path / "Caches" / "AzurKit")):
        monkeypatch.setattr(platformdirs, "user_cache_path", lambda *_, at=cache, **__: at)
        assert ghidra_serve.state_root() == root / "ghidra-serve"
        with ghidra_apply._work(None) as work:
            assert Path(work).parent == root / "ghidra-apply"


def test_a_serve_reuses_its_copy_only_while_the_project_and_the_copy_are_unchanged(tmp_path, monkeypatch):
    """Q202: the copy is reused only while the project and the copy both
    match its stamp, and the project is only ever read. A project that
    changes during the copy (the owner's GUI saving) is copied once more,
    then refused, keeping the last good copy."""
    gpr = project(tmp_path / "src")
    db = gpr.with_suffix(".rep") / "idata" / "00" / "00000000.gbf"
    port_dir = tmp_path / "state" / "8212"

    def ensure() -> str:
        before = hashes(gpr.parent)
        copy, how = ghidra_serve.ensure_copy(gpr, port_dir)
        assert hashes(gpr.parent) == before
        assert hashes(copy.with_suffix(".rep")) == {k: v for k, v in hashes(gpr.with_suffix(".rep")).items()}
        return how

    assert [ensure(), ensure()] == ["copied (first copy)", "reused"]
    db.write_bytes(b"db saved by the owner")
    assert [ensure(), ensure()] == ["copied (the project changed)", "reused"]
    copy_db = port_dir / "project" / "AzurikServe.rep" / "idata" / "00" / "00000000.gbf"
    copy_db.write_bytes(b"db changed in the copy")
    assert ensure() == "copied (the copy changed)"
    shutil.rmtree(copy_db.parents[2])  # a copy torn by an interrupted re-copy: no .rep
    assert ensure() == "copied (the copy changed)"

    real_copy, saves = ghidra_serve.copy_project, []

    def copy_during_a_save(project_, dest, name, *, times):
        new = real_copy(project_, dest, name)
        if len(saves) < times:
            saves.append(f"save {len(saves) + 1}")
            db.write_bytes(saves[-1].encode())
        return new

    db.write_bytes(b"db saved again")
    monkeypatch.setattr(ghidra_serve, "copy_project", lambda *a: copy_during_a_save(*a, times=99))
    with pytest.raises(ghidra_serve.ServeError, match="changed while it was copied, twice"):
        ghidra_serve.ensure_copy(gpr, port_dir)
    assert (saves, copy_db.read_bytes(), (port_dir / "project.new").exists()) == (
        ["save 1", "save 2"], b"db saved by the owner", False)
    saves.clear()
    monkeypatch.setattr(ghidra_serve, "copy_project", lambda *a: copy_during_a_save(*a, times=1))
    assert ghidra_serve.ensure_copy(gpr, port_dir)[1] == "copied (the project changed)"
    assert copy_db.read_bytes() == b"save 1"


@SOCKETS
def test_a_serve_runs_a_read_only_copy_headless_on_loopback_and_stop_ends_it(serve):
    """``start`` runs analyzeHeadless on the copy, never the project, with
    -readOnly and the serve script, its settings and temp in the state
    folder and the bind host 127.0.0.1; ``status`` and ``stop`` follow it.
    A second start and a start on a port something else answers (here an
    SSH-like banner) are refused with nothing written."""
    gpr, root, port, headless = serve.gpr, serve.root, serve.port, serve.headless
    record = json.loads(serve.record.read_text(encoding="utf-8"))
    argv, state = record["argv"], root / str(port) / "run"
    assert argv[:2] == [str(root / str(port) / "project"), "AzurikServe"]
    assert str(gpr.parent) not in " ".join(argv)
    assert {"-readOnly", "-noanalysis"} <= set(argv)
    assert argv[argv.index("-postScript") + 1] == "AzurikServe.java"
    assert argv[argv.index("-scriptPath") + 1] == str(ghidra_serve.SCRIPTS)
    options = f" {record['options']} "  # as substrings: a temp dir may hold a space
    assert [o for o in (f"-Dapplication.settingsdir={state / 'settings'}", f"-Djava.io.tmpdir={state / 'tmp'}",
                        "-Dghidra.mcp.bind.host=127.0.0.1") if f" {o} " not in options] == []
    assert record["bind"] == "127.0.0.1"
    assert GhidraClient(port=port).ping()
    status = ghidra_serve.status(port, root)
    assert (status["running"], status["dirty"], status["stale"], status["lock"]) == (True, False, False,
                                                                                     LockState("free"))

    class Banner(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.sendall(b"SSH-2.0-OpenSSH_9.9\r\n")

    before = hashes(root)
    with pytest.raises(ghidra_serve.ServeError, match=f"already serving a copy on port {port}"):
        ghidra_serve.start(gpr, port, root=root, headless=headless)
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Banner) as busy:
        threading.Thread(target=busy.serve_forever, daemon=True).start()
        try:
            with pytest.raises(ghidra_serve.ServeError,
                               match=f"port {busy.server_address[1]} is busy: something that is not Ghidra"):
                ghidra_serve.start(gpr, busy.server_address[1], root=root, headless=headless)
        finally:
            busy.shutdown()
    assert hashes(root) == before
    assert ghidra_serve.stop(port, root, timeout=30) == {"port": port, "stopped": True, "how": "stop file"}
    with socket.socket() as s:
        assert serve.proc.poll() is not None and s.connect_ex(("127.0.0.1", port)) != 0
    assert ghidra_serve.status(port, root) == {"port": port, "running": False}


@SOCKETS
def test_the_snapshot_refuses_a_serve_that_is_dirty_or_stale(serve, monkeypatch, capsys):
    """Modkit's decision 7: ``ghidra-snapshot --port N`` reads a clean,
    current serve as usual, and exits 2 naming the state, writing nothing,
    once the serve holds in-memory edits (dirty: refused before the dump; an
    edit made during the dump is caught before the write) or the project
    changed since the copy (stale)."""
    ready = serve.root / str(serve.port) / "run" / "ready.json"
    dumps, real_dump = [], ghidra_snapshot.dump_snapshot

    def dump(*args, edit_during=False, **kwargs):
        dumps.append(edit_during)
        got = real_dump(*args, **kwargs)
        if edit_during:  # another client renames something while the dump runs
            ready.write_text(json.dumps({"readyModificationNumber": 7, "modificationNumber": 8}), encoding="utf-8")
        return got

    def snapshot(name: str, *, edit_during: bool = False) -> tuple[int, bool, bool, bool]:
        monkeypatch.setattr(ghidra_snapshot, "dump_snapshot", lambda *a, **k: dump(*a, edit_during=edit_during, **k))
        path = serve.root.parent / name
        code, _, err = run(capsys, ghidra_snapshot, str(path), "--port", str(serve.port))
        return code, "is dirty" in err, "is stale" in err, path.exists()

    def state() -> tuple[bool, bool]:
        s = ghidra_serve.status(serve.port, serve.root)
        return s["dirty"], s["stale"]

    assert (state(), snapshot("clean.json")) == ((False, False), (0, False, False, True))
    assert (snapshot("edited_during.json", edit_during=True), state()) == ((2, True, False, False), (True, False))
    dumps.clear()
    assert (snapshot("dirty.json"), dumps) == ((2, True, False, False), [])
    ready.write_text(json.dumps({"readyModificationNumber": 7, "modificationNumber": 7}), encoding="utf-8")
    (serve.gpr.with_suffix(".rep") / "project.prp").write_bytes(b"prp saved by the owner")
    assert (state(), snapshot("stale.json")) == ((False, True), (2, False, True, False))


def test_status_and_stop_never_take_a_process_that_reused_an_ended_serves_pid(tmp_path):
    """A serve that ended by itself (``--max-seconds``, a crash, a reboot)
    leaves ``serve.json`` behind. Once another process reuses its pid (here
    a session leader of its own), ``status`` says not running,
    ``ghidra-snapshot`` reads the port as usual and ``stop`` signals
    nothing: the pid alone never names the serve."""
    root, port = tmp_path / "state", free_port()
    (root / str(port) / "run").mkdir(parents=True)
    detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
              else {"start_new_session": True})
    with subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(120)"], **detach) as other:
        try:
            (root / str(port) / "serve.json").write_text(json.dumps(
                {"pid": other.pid, "identity": "the ended serve's start time", "port": port,
                 "project": str(tmp_path / "Azurik Ghidra.gpr")}), encoding="utf-8")
            assert ghidra_serve.status(port, root) == {"port": port, "running": False}
            assert ghidra_serve.unfit_for_snapshot(port, root) is None
            assert ghidra_serve.stop(port, root, timeout=1) == {"port": port, "stopped": True,
                                                                "how": "had already exited"}
            assert (other.poll(), (root / str(port) / "serve.json").exists()) == (None, False)
        finally:
            other.kill()


@SOCKETS
@pytest.mark.parametrize("at", ["launch", "wait"])
def test_an_interrupted_start_leaves_nothing_running(tmp_path, monkeypatch, at):
    """D35: a start interrupted (Ctrl-C, or a test's timeout) as soon as the
    serve is launched, or while it waits for the serve, ends the detached
    serve and removes ``serve.json``, instead of leaving it running for its
    whole lifetime, even when a second Ctrl-C (``uv run`` passes one on)
    lands during that cleanup."""
    gpr, root, port = project(tmp_path / "src"), tmp_path / "state", free_port()
    fake = tmp_path / "never_serves.py"
    fake.write_text("import sys, time\nargv = sys.argv[1:]\n"
                    "open(argv[argv.index('AzurikServe.java') + 3], 'w').close()\ntime.sleep(120)\n",
                    encoding="utf-8")
    real_identity, real_alive = ghidra_serve._identity, ghidra_serve._group_alive
    pids, again = [], []

    def identity(pid: int) -> str | None:  # start asks as soon as Popen returns
        pids.append(pid)
        if at == "launch" and len(pids) == 1:
            raise KeyboardInterrupt
        return real_identity(pid)

    def ctrl_c(port_: int):  # start asks once the ready file exists
        raise KeyboardInterrupt

    def ctrl_c_again(pid: int) -> bool:  # the cleanup's first question
        if not again:
            again.append(pid)
            raise KeyboardInterrupt
        return real_alive(pid)

    monkeypatch.setattr(ghidra_serve, "_identity", identity)
    monkeypatch.setattr(ghidra_serve, "_program_at", ctrl_c)
    monkeypatch.setattr(ghidra_serve, "_group_alive", ctrl_c_again)
    with pytest.raises(KeyboardInterrupt):
        ghidra_serve.start(gpr, port, root=root, headless=[sys.executable, "-I", str(fake)], timeout=60)
    assert real_identity(pids[0]) is None
    assert again and not (root / str(port) / "serve.json").exists()


# ---------------------------------------------------------------------------
# bootstrap.py --with re
# ---------------------------------------------------------------------------


def fake_re_checkout(tmp_path: Path, bad_sha256_for: str | None = None) -> tuple[Path, Path]:
    """A checkout whose tools.toml points at local copies of the 3 asset kinds."""
    src, root = tmp_path / "src", tmp_path / "repo"
    src.mkdir(parents=True)
    (root / "devkit" / "re").mkdir(parents=True)
    with zipfile.ZipFile(src / "ghidra.zip", "w") as z:
        z.writestr(zipfile.ZipInfo("ghidra_12.1.2_PUBLIC/support/launch.properties"), "VMARGS=-Xshare:off\n")
        launcher = zipfile.ZipInfo("ghidra_12.1.2_PUBLIC/ghidraRun")
        launcher.external_attr = 0o100755 << 16
        z.writestr(launcher, "#!/bin/sh\n")
    with tarfile.open(src / "jdk.tar.gz", "w:gz") as t:
        java = tarfile.TarInfo("jdk-25.0.4.1+1/Contents/Home/bin/java")
        java.mode, java.size = 0o755, 0
        t.addfile(java, io.BytesIO())
    with zipfile.ZipFile(src / "ghydra.zip", "w") as z:
        z.writestr("Ghydra/extension.properties", "name=Ghydra\n")
    (src / "bridge_mcp_hydra.py").write_text("# bridge\n", encoding="utf-8")
    toml = ["schema = 1"]
    for name, kind, file, host in [("ghidra", "archive", "ghidra.zip", "any"),
                                   ("jdk", "archive", "jdk.tar.gz", bootstrap.host_platform()),
                                   ("ghydra", "ghidra-extension", "ghydra.zip", "any"),
                                   ("ghydra-bridge", "file", "bridge_mcp_hydra.py", "any")]:
        sha = "0" * 64 if name == bad_sha256_for else hashlib.sha256((src / file).read_bytes()).hexdigest()
        toml += [f"[tools.{name}]", 'version = "1"', f'kind = "{kind}"',
                 f'assets.{host} = {{ url = "{(src / file).as_uri()}", sha256 = "{sha}" }}',
                 'assets.windows-arm64 = { url = "https://example.invalid/x.zip", sha256 = "" }']
    (root / "devkit" / "re" / "tools.toml").write_text("\n".join(toml) + "\n", encoding="utf-8")
    return src, root


def test_bootstrap_with_re_installs_each_verified_tool_binds_ghidra_to_loopback_and_refuses_an_unverified_one(
        tmp_path):
    """``bootstrap.py --with re`` fetches each tools.toml entry for the host,
    checks its sha256 before unpacking it (a mismatch or a missing hash
    installs nothing of it), keeps the zip's exec bits, unzips the plugin
    into Ghidra, stamps ``.ok`` so a re-run fetches nothing unchanged, and
    rewrites one managed block of launch.properties: the JDK, Ghidra's
    folders in ``.tools/ghidra-home``, the plugin bound to 127.0.0.1 (Q171,
    AZ-153), scripts only with ``--allow-scripts``. It prints the bridge's
    ``claude mcp add`` line: the bridge in ``ghidra_bridge.py``'s locked
    script environment, its host the IPv4 loopback. The real pins are devkit/re/tools.toml's: Ghidra
    12.1.2, Temurin 25, GhydraMCP 3.0.0-rc.1, ghidra-xbe and the Xbox SDK headers (GPL-2, Step 4.24c),
    the last two download only."""
    import tomllib
    pins = tomllib.loads((ROOT / "devkit" / "re" / "tools.toml").read_text(encoding="utf-8"))["tools"]
    assert {name: tool["version"] for name, tool in pins.items()} == {
        "ghidra": "12.1.2", "jdk": "25.0.4.1+1", "ghidra-xbe": "build-202602250354", "ghydra": "3.0.0-rc.1",
        "ghydra-bridge": "3.0.0-rc.1", "xbox-includes": "0f8e2521684a"}
    src, root = fake_re_checkout(tmp_path)
    line = bootstrap.install_re(root, allow_scripts=False)
    tools = root / ".tools"
    assert sorted(p.name for p in tools.iterdir()) == ["ghidra", "ghidra-home", "ghydra", "ghydra-bridge", "jdk"]
    for name, file in [("ghidra", "ghidra.zip"), ("jdk", "jdk.tar.gz"), ("ghydra", "ghydra.zip"),
                       ("ghydra-bridge", "bridge_mcp_hydra.py")]:
        assert (tools / name / ".ok").read_text(encoding="utf-8") == (
            f"1 {hashlib.sha256((src / file).read_bytes()).hexdigest()}\n")
    assert os.access(tools / "ghidra" / "ghidraRun", os.X_OK), "zip exec bits kept"
    assert (tools / "ghidra" / "Ghidra" / "Extensions" / "Ghydra" / "extension.properties").is_file()
    home = (tools / "ghidra-home").as_posix()
    assert (tools / "ghidra" / "support" / "launch.properties").read_text(encoding="utf-8").splitlines() == [
        "VMARGS=-Xshare:off", "", bootstrap.MANAGED,
        f"JAVA_HOME_OVERRIDE={(tools / 'jdk' / 'Contents' / 'Home').as_posix()}",
        f"VMARGS=-Dapplication.settingsdir={home}", f"VMARGS=-Dapplication.cachedir={home}/cache",
        f"VMARGS=-Dghidra.user.scripts.dir={home}",
        "VMARGS=-Dghidra.mcp.bind.host=127.0.0.1", "VMARGS=-Dghidra.mcp.cors.origin=http://127.0.0.1:1"]
    assert line == ("claude mcp add --scope local ghidra -e GHIDRA_HYDRA_HOST=127.0.0.1 -- uv run --locked --script "
                    f"{(root / 'devkit' / 're' / 'ghidra_bridge.py').as_posix()} "
                    f"{(tools / 'ghydra-bridge' / 'bridge_mcp_hydra.py').as_posix()}")
    shutil.rmtree(src)  # a re-run fetches nothing whose .ok stamp matches
    bootstrap.install_re(root, allow_scripts=True)
    props = (tools / "ghidra" / "support" / "launch.properties").read_text(encoding="utf-8").splitlines()
    assert (props.count(bootstrap.MANAGED), props[-1]) == (1, "VMARGS=-Dghydra.dev.allowScripts=true")

    _, root = fake_re_checkout(tmp_path / "bad", bad_sha256_for="jdk")
    with pytest.raises(SystemExit, match="jdk: the download's sha256 is .* tools.toml pins 0000"):
        bootstrap.install_re(root, allow_scripts=False)
    assert sorted(p.name for p in (root / ".tools").iterdir()) == ["ghidra"], "no jdk, no temp debris"
    (root / "devkit" / "re" / "tools.toml").write_text(
        'schema = 1\n[tools.ghydra-bridge]\nversion = "1"\nkind = "file"\n'
        'assets.any = { url = "https://example.invalid/b.py", sha256 = "" }\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="no .* asset with a sha256 for ghydra-bridge"):
        bootstrap.install_re(root, allow_scripts=False)


def test_the_pins_workflow_hashes_again_only_the_tools_toml_assets_a_pull_request_alters_and_fails_a_wrong_hash(
        tmp_path, monkeypatch, capsys):
    """Modkit's pins workflow (Step 4.24c): ``.github/workflows/pins.yml``
    runs only on a pull request that changes ``devkit/re/tools.toml`` or
    ``bootstrap.py``, and runs ``bootstrap.py --verify-pins`` against the
    base commit's tools.toml with no project synced; that downloads only the
    assets the change adds or alters (an unchanged one isn't fetched) and
    names each whose sha256 isn't the download's, exit 1."""
    pins = (ROOT / ".github" / "workflows" / "pins.yml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^on:\n  pull_request:\n    paths: \[devkit/re/tools.toml, bootstrap.py\]\n\n", pins)
    assert ('uv run --no-project --python 3.14 python -I bootstrap.py --verify-pins "$RUNNER_TEMP/base-tools.toml"'
            in pins)
    src, root = fake_re_checkout(tmp_path)
    good = (root / "devkit" / "re" / "tools.toml").read_text(encoding="utf-8")
    jdk = hashlib.sha256((src / "jdk.tar.gz").read_bytes()).hexdigest()
    for unchanged in ("ghidra.zip", "ghydra.zip", "bridge_mcp_hydra.py"):
        (src / unchanged).unlink()   # fetching one would fail the run
    base = tmp_path / "base.toml"
    base.write_text(good, encoding="utf-8")
    assert bootstrap.verify_pins(good, good) == []
    monkeypatch.setattr(bootstrap, "ROOT", root)
    (root / "devkit" / "re" / "tools.toml").write_text(good.replace(jdk, "0" * 64), encoding="utf-8")
    assert bootstrap.main(["--verify-pins", str(base)]) == 1
    assert capsys.readouterr().err == (f"pins: jdk {bootstrap.host_platform()}: the download's sha256 is {jdk}, "
                                       f"tools.toml pins {'0' * 64}\n")


def test_sdk_headers_writes_the_fetched_xbox_headers_copy_ghidra_imports_and_with_none_fetched_is_one_line(
        tmp_path, monkeypatch, capsys):
    """Modkit's ``vendor/xbox-includes`` (GPL-2) isn't in the repository:
    ``bootstrap.py --with re`` fetches mborgerson/xbox-includes (its pin
    above) and ``devkit re sdk-headers`` writes the copy Ghidra's
    ``ImportHeader`` reads beside it (Modkit's ``_patch_xboxkrnl_ghidra.py``,
    Step 4.24c): ``xboxdef.h`` as the SDK's base types under ``XBX_`` names,
    the bridge header defining the SDK's names as those, and ``xboxkrnl.h``
    with the bridge included, no pragma, no ``extern "C"`` block and each
    type-and-pointer typedef split in two; every other header as fetched.
    It prints the import's arguments. With nothing fetched it is one line
    and exit 2."""
    monkeypatch.setattr(sdk_headers, "tools_dir", lambda: tmp_path)
    assert sdk_headers.main([]) == 2 and capsys.readouterr().err.count("\n") == 1
    include = tmp_path / "xbox-includes" / "include"
    include.mkdir(parents=True)
    (include / "xapi.h").write_text("int x;\n", encoding="utf-8")
    (include / "xboxdef.h").write_text("typedef void *PVOID;\n", encoding="utf-8")
    (include / "xboxkrnl.h").write_text(
        '#include "xboxdef.h"\n#pragma pack(1)\n#if defined(__cplusplus)\nextern "C"\n{\n#endif\n'
        "typedef struct _A {\n    int a;\n} A, *PA;\ntypedef UCHAR KIRQL, *PKIRQL;\n"
        "#if defined(__cplusplus)\n}\n#endif\n", encoding="utf-8")
    assert sdk_headers.main([]) == 0
    out = tmp_path / "xbox-includes" / "ghidra"
    assert sorted(p.name for p in out.iterdir()) == ["xapi.h", "xboxdef.h", "xboxkrnl.h", "xboxkrnl_ghidra_bridge.h"]
    krnl = (out / "xboxkrnl.h").read_text(encoding="utf-8")
    assert '#include "xboxdef.h"\n#include "xboxkrnl_ghidra_bridge.h"\n' in krnl
    assert "#pragma" not in krnl and 'extern "C"' not in krnl
    assert "} A;\ntypedef A *PA;" in krnl and "typedef UCHAR KIRQL;\ntypedef UCHAR *PKIRQL;" in krnl
    assert (out / "xapi.h").read_text(encoding="utf-8") == "int x;\n"
    assert "typedef unsigned int XBX_PVOID;" in (out / "xboxdef.h").read_text(encoding="utf-8")
    assert "#define PVOID          XBX_PVOID" in (out / "xboxkrnl_ghidra_bridge.h").read_text(encoding="utf-8")
    assert f'"{(out / "xboxkrnl.h").as_posix()}", "-I{out.as_posix()}"' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The GhidraScripts in the real Ghidra (marked ghidra)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def headless() -> Path:
    """``.tools``' analyzeHeadless (:func:`devkit.re.ghidra_serve.tools_dir`).
    A run that selects a ``ghidra`` test without it fails, naming the fix:
    never a skip (the allow-list is empty)."""
    exe = ghidra_serve.headless_exe()
    if not exe.is_file():
        pytest.fail(f'the ghidra tests need Ghidra in {exe.parents[2]}: run `uv run bootstrap.py --with re` in the '
                    'main checkout, or deselect them with -m "not ghidra"', pytrace=False)
    return exe


def ghidra_run(cmd: list, d: Path) -> subprocess.CompletedProcess:
    """Run analyzeHeadless with Ghidra's settings, cache and temp under ``d``
    (only its launcher rewrites ``.tools/ghidra-home``'s ``java_home.save``,
    with the same JDK)."""
    vmargs = (f"-Dapplication.settingsdir={d / 'home'} -Dapplication.cachedir={d / 'home/cache'}"
              f" -Dghidra.user.scripts.dir={d / 'home'} -Djava.io.tmpdir={d / 'tmp'} -Duser.home={d / 'home'}")
    for sub in ("proj", "home", "tmp", "scripts"):
        (d / sub).mkdir(exist_ok=True)
    return subprocess.run([str(c) for c in cmd], env={**os.environ, "GHIDRA_HEADLESS_JAVA_OPTIONS": vmargs},
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)


def blob_project(headless: Path, d: Path, *script: str) -> subprocess.CompletedProcess:
    """A project ``Blob`` in ``d/proj`` holding a 256-byte zero blob as x86
    code, after ``script``'s post-scripts."""
    (d / "blob.bin").write_bytes(bytes(256))
    return ghidra_run([headless, d / "proj", "Blob", "-import", d / "blob.bin", "-loader", "BinaryLoader",
                       "-processor", "x86:LE:32:default", "-noanalysis", *script], d)


DUMP = """\
import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.Category;
import ghidra.program.model.data.DataType;

public class DumpTypes extends GhidraScript {
	@Override
	protected void run() throws Exception {
		walk(currentProgram.getDataTypeManager().getRootCategory());
	}

	private void walk(Category c) {
		println("CAT " + c.getCategoryPath().getPath());
		for (DataType dt : c.getDataTypes()) {
			println("TYPE " + dt.getPathName());
		}
		for (Category sub : c.getCategories()) {
			walk(sub);
		}
	}
}
"""


@pytest.mark.ghidra
def test_import_header_files_types_under_its_category_and_a_header_it_cannot_read_imports_nothing(
        headless, tmp_path):
    """AZ-036: imported twice, the probe is one type at /Cat/T, and no
    per-file category (/inline.h, /Cat/<file>.h) is left. A preprocessor
    error (which Ghidra's parser returns, not throws), a mistyped .h path and
    a C syntax error each fail their script run and import nothing."""
    bad = {"/AzurikBroken": ("#error boom\nstruct AzurikBrokenProbe { int a; };", "parse failed"),
           "/AzurikMissing": ("/no/such/dir/azurik.h", "no such header"),
           "/AzurikSyntax": ("struct AzurikSyntaxProbe { int a;", "ParseException")}
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "DumpTypes.java").write_text(DUMP, encoding="utf-8")
    cmd = ["-deleteProject", "-scriptPath", f"{ghidra_serve.SCRIPTS};{tmp_path / 'scripts'}"]
    for category, header in [("/AzurikSmokeTest", "struct AzurikSmokeTestProbe { int a; int b; };")] * 2 + [
            (c, h) for c, (h, _) in bad.items()]:
        cmd += ["-postScript", "ImportHeader.java", category, header]
    log = blob_project(headless, tmp_path, *cmd, "-postScript", "DumpTypes.java")
    assert log.returncode == 0, log.stdout[-4000:]
    paths = re.findall(r"DumpTypes\.java> (?:CAT|TYPE) (\S+)", log.stdout)
    assert [p for p in paths if p.endswith("/AzurikSmokeTestProbe")] == ["/AzurikSmokeTest/AzurikSmokeTestProbe"]
    assert not [p for p in paths if re.search(r"Azurik(Broken|Missing|Syntax)|\.h", p)], paths
    for category, (_, error) in bad.items():
        ran = next(r for r in log.stdout.split("REPORT: Execute script: ")
                   if r.startswith(f"ImportHeader.java '{category}'"))
        assert "SCRIPT ERROR" in ran and error in ran, ran[-2000:]


@pytest.mark.ghidra
@SOCKETS
def test_a_headless_serve_answers_the_client_on_loopback_only_and_saves_nothing(headless, tmp_path):
    """AZ-193: ``ghidra-serve``'s real start (``-process … -readOnly`` and
    ``AzurikServe.java``) on a project file serves 127.0.0.1 only, takes a
    comment into memory (``status`` says dirty), and neither save route
    persists it: the copy it served is unchanged after stop."""
    made = blob_project(headless, tmp_path)
    assert made.returncode == 0, made.stdout[-4000:]
    gpr, root, port = tmp_path / "proj" / "Blob.gpr", tmp_path / "serve", free_port()
    before = ghidra_project.fingerprint(gpr)
    # max_seconds: a serve a killed run leaves behind ends by itself
    ghidra_serve.start(gpr, port, root=root, program="blob.bin", timeout=120, max_seconds=600)
    try:
        log = (root / str(port) / "run" / "headless.log").read_text(encoding="utf-8")
        assert f"GhydraMCP HTTP server started on 127.0.0.1:{port}" in log
        try:  # this host's LAN address (a UDP connect sends nothing)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("192.0.2.1", 9))
                lan = probe.getsockname()[0]
        except OSError:  # no network: the log line above is the check
            lan = "127.0.0.1"
        with socket.socket() as s:
            s.settimeout(5)  # a stealth firewall drops the SYN to a closed port
            assert lan.startswith("127.") or s.connect_ex((lan, port)) != 0, lan
        client = GhidraClient(port=port, timeout=30)
        set_ = client._request("POST", "/memory/00000000/comments/plate", json_body={"comment": "AzurikSmokeTest"}).body
        got = client._request("GET", "/memory/00000000/comments/plate").body
        assert set_["success"] and got["result"]["comment"] == "AzurikSmokeTest", (set_, got)
        deadline = time.monotonic() + 10
        while not ghidra_serve.status(port, root)["dirty"] and time.monotonic() < deadline:
            time.sleep(0.25)
        assert "dirty" in ghidra_serve.unfit_for_snapshot(port, root)
        saves = [client._request("POST", f"/{route}").body for route in ("program/save", "programs/save")]
    finally:
        stopped = ghidra_serve.stop(port, root, timeout=20)
    assert stopped["how"] == "stop file"
    stamp = json.loads((root / str(port) / "stamp.json").read_text(encoding="utf-8"))["fingerprint"]
    assert ([s.get("result", {}).get("saved") for s in saves],
            ghidra_project.fingerprint(root / str(port) / "project" / "AzurikServe.gpr")) == ([False, False], stamp)
    assert ghidra_project.fingerprint(gpr) == before == stamp


# Gives the apply test's blob what a plan line changes: a function, a label
# (at 0xC0, as a GUI rename leaves one: user-defined), an equate and a
# category (with a subcategory, and a struct applied as data at 0x80, where
# the function's code stops).
SEED = """\
import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.CategoryPath;
import ghidra.program.model.data.StructureDataType;

public class Seed extends GhidraScript {
	@Override
	protected void run() throws Exception {
		createData(toAddr(0x80), currentProgram.getDataTypeManager().addDataType(
			new StructureDataType(new CategoryPath("/AzurikSmokeTest"), "AzurikSmokeTestStruct", 4), null));
		disassemble(toAddr(0));
		createFunction(toAddr(0), "AzurikSmokeTestFn");
		createLabel(toAddr(0xC0), "AzurikSmokeTestLabel", true);
		currentProgram.getEquateTable().createEquate("AZURIK_SMOKETEST_ONE", 1);
		currentProgram.getDataTypeManager().createCategory(new CategoryPath("/AzurikSmokeTest/sub"));
	}
}
"""


@pytest.mark.ghidra
def test_apply_plan_writes_a_plan_into_a_closed_project_and_rolls_back_a_failing_one(headless, tmp_path):
    """D90: ``ghidra-apply``'s real runs (``ApplyPlan.java`` under
    analyzeHeadless; success read from its markers) on a project file. The
    dry run on a copy lists the six lines pending and leaves the project
    alone; the apply backs it up, renames the function and the label
    (AZ-252: a label that is not a function), comments, deletes the equate
    and the category (with the data its struct is applied to), creates a
    function where nothing was code, and its verify on a copy finds all six
    in effect. A create inside a function fails the dry run. A plan that
    contradicts itself applies both lines, fails the in-memory check and
    rolls back; the run exits 0 and still saves, and the backup goes back."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "Seed.java").write_text(SEED, encoding="utf-8")
    made = blob_project(headless, tmp_path, "-scriptPath", tmp_path / "scripts", "-postScript", "Seed.java")
    assert made.returncode == 0 and "SCRIPT ERROR" not in made.stdout, made.stdout[-4000:]
    gpr, work = tmp_path / "proj" / "Blob.gpr", tmp_path / "work"
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps([
        {"op": "rename", "va": "0x0", "from": "AzurikSmokeTestFn", "to": "AzurikSmokeTestFn2"},
        {"op": "rename_label", "va": "0xC0", "from": "AzurikSmokeTestLabel", "to": "AzurikSmokeTestLabel2"},
        {"op": "comment", "va": "0x0", "kind": "plate", "text": "AzurikSmokeTest"},
        {"op": "delete_equate", "name": "AZURIK_SMOKETEST_ONE"},
        {"op": "delete_category", "path": "/AzurikSmokeTest"},
        {"op": "create_function", "va": "0xA0", "name": "AzurikSmokeTestNew"}]), encoding="utf-8")
    before = manifest(gpr)
    dry = ghidra_apply.dry_run(gpr, plan, program="blob.bin", work_root=work)
    assert dry["lines"] == [
        'AZPLAN: pending rename 00000000 "AzurikSmokeTestFn" -> "AzurikSmokeTestFn2"',
        'AZPLAN: pending rename_label 000000c0 "AzurikSmokeTestLabel" -> "AzurikSmokeTestLabel2"',
        'AZPLAN: pending comment 00000000 plate "AzurikSmokeTest" (none before)',
        'AZPLAN: pending delete_equate "AZURIK_SMOKETEST_ONE" = 0x1 (0 references)',
        'AZPLAN: pending delete_category "/AzurikSmokeTest" (1 types, 1 subcategories; '
        "used by 1 data, 0 functions, 0 other types)",
        'AZPLAN: pending create_function 000000a0 "AzurikSmokeTestNew", not code yet',
        "AZPLAN: DRY 6 of 6 pending"], dry
    assert manifest(gpr) == before
    r = ghidra_apply.apply_plan(gpr, plan, ghidra_apply.plan_sha256(plan), program="blob.bin", work_root=work)
    assert (r["applied"], r["verified"]) == (True, True), r
    assert manifest(Path(r["backup"]) / gpr.name) == before != manifest(gpr)
    assert "AZVERIFY: OK 6 lines in effect" in (Path(r["backup"]) / "verify.log").read_text(encoding="utf-8")
    inside = tmp_path / "inside.json"
    inside.write_text(json.dumps([{"op": "create_function", "va": "0x10"}]), encoding="utf-8")
    with pytest.raises(ApplyError, match='00000010 is inside the function "AzurikSmokeTestFn2" at 00000000'):
        ghidra_apply.dry_run(gpr, inside, program="blob.bin", work_root=work)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"op": "comment", "va": "0x0", "kind": "eol", "text": text} for text in ("one", "two")]),
                   encoding="utf-8")
    applied = manifest(gpr)
    r = ghidra_apply.apply_plan(gpr, bad, ghidra_apply.plan_sha256(bad), program="blob.bin", work_root=work)
    assert (r["applied"], r["verified"], r["lines"][-1]) == (False, False, "AZPLAN: ROLLED BACK"), r
    assert "plan line 1 is not in effect after the apply" in r["why"]
    assert (r["restored"], manifest(gpr)) == (True, applied)  # the failed run saved; the backup went back
