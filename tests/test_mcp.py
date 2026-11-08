"""The azurik MCP server (``devkit/mcp``, ``docs/MCP.md``; Step 4.11f, ported
from Modkit's ``azurik_mod/mcp``): ``.mcp.json``'s command serves the 8 tools
over stdio, on a wire nothing a tool prints reaches (AZ-154), each tool answers
in its envelope on the USA image without clamping a value (D23), and a refusal
names what it refuses, with nothing written (D35, D36)."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from devkit.mcp import tools
from tests import _xiso

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["entity_get", "entity_list", "iso_extract", "iso_repack", "pack_build_iso", "pack_list", "rando_build_iso",
         "xbr_edit"]   # D64's
NOISY = """\
import os
from devkit.mcp import serve

def noisy() -> dict:
    print("a tool's print")
    os.write(1, b"a child's write to fd 1\\n")
    return {"success": True, "result": None}

serve.SERVER.add_tool(noisy)
raise SystemExit(serve.main([]))
"""


def session(argv: list[str], calls: list[tuple[str, dict]]) -> list[dict]:
    """The replies of a server started with ``argv`` to the handshake and each
    call, each the next line of its stdout and nothing else on it."""
    def request(k: int, method: str, params: dict) -> str:
        return json.dumps({"jsonrpc": "2.0", "id": k, "method": method, "params": params}) + "\n"
    hello = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "0"}}
    replies = []
    with tempfile.TemporaryFile("w+", encoding="utf-8") as log, subprocess.Popen(
            argv, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
            encoding="utf-8") as proc:
        def said() -> str:   # the server's stderr's tail, for a failure's message
            log.seek(0)
            return log.read()[-2000:]
        for k, (method, params) in enumerate([("initialize", hello), *calls]):
            proc.stdin.write(request(k, method, params))
            if k == 0:
                proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            assert line.startswith("{") and json.loads(line).get("id") == k, (line[:300], said())
            replies.append(json.loads(line)["result"])
        proc.stdin.close()
        assert proc.stdout.read() == "", said()
    return replies[1:]


def answer(reply: dict) -> dict:
    return json.loads(reply["content"][0]["text"])


def test_the_mcp_json_command_serves_the_eight_tools_on_a_wire_no_print_reaches():
    server = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["azurik"]
    listed, found = session([shutil.which(server["command"]), *server["args"]], [
        ("tools/list", {}),
        ("tools/call", {"name": "pack_list", "arguments": {"category": None, "pack": "fps_unlock"}})])
    assert sorted(t["name"] for t in listed["tools"]) == NAMES
    assert [p["name"] for p in answer(found)["result"]] == ["fps_unlock"]   # an explicit null takes the default
    noisy = session([sys.executable, "-c", NOISY], [("tools/call", {"name": "noisy", "arguments": {}})] * 2)
    assert [answer(reply)["success"] for reply in noisy] == [True, True]


def ok(reply: dict):
    assert reply["success"], reply
    return reply["result"]


def test_each_tool_answers_in_its_envelope_on_the_usa_image_and_writes_a_value_unclamped(usa_iso, tmp_path):
    image = str(usa_iso)
    assert ok(tools.entity_list(image))["critters_flocking"] == 26
    assert "air_elemental" in ok(tools.entity_list(image, "critters_flocking"))
    catalisk = ok(tools.entity_get(image, "Catalisk", "damage"))   # D51: as a mods file spells it
    assert catalisk["entity"] == "catalisk" and "Damage" in catalisk["properties"]
    assert list(ok(tools.entity_get(image, "KingKong"))["ambiguous"]) == ["critters_maya_stuff"]
    tree = tmp_path / "tree"
    assert ok(tools.iso_extract(image, str(tree), ["GAMEDATA/CONFIG.XBR"]))["files"] == 1
    config, edited = tree / "gamedata" / "config.xbr", tmp_path / "edited.xbr"
    level = {"op": "set", "table": "armor_properties", "entity": "no_armor_1", "prop": "Level", "value": 999999}
    assert ok(tools.xbr_edit(str(config), str(edited), [level]))["ops_applied"] == 1
    os.replace(edited, config)
    (tree / ".DS_Store").write_bytes(b"Bud1")   # the host's, skipped
    packed = ok(tools.iso_repack(str(tree), str(tmp_path / "repacked.iso")))
    assert (packed["region"], packed["files_changed"]) == ("usa", ["gamedata/config.xbr"])
    assert ok(tools.entity_get(packed["out"], "no_armor_1", "armor_properties"))["properties"]["Level"] == 999999
    Path(packed["out"]).unlink()
    [hp] = ok(tools.pack_list(pack="player_max_hp"))
    assert hp["sliders"][0]["xbr"] == {"file": "gamedata/config.xbr", "table": "settings_foo", "entity": "initial hp",
                                       "prop": "Value"}
    built = ok(tools.rando_build_iso(image, str(tmp_path / "seed.iso"), 2, {
        "enable": ["player_max_hp"], "params": {"player_max_hp": {"starting_hp": 500}},
        "spoiler": str(tmp_path / "spoiler.txt")}))   # the file's one build
    assert (built["region"], built["randomizer"]["seed"]) == ("usa", "2")
    assert "player_max_hp" in built["summary"]["packs_applied"] and (tmp_path / "spoiler.txt").stat().st_size
    assert ok(tools.entity_get(built["output_path"], "initial hp", "settings_foo"))["properties"]["Value"] == 500


def test_a_refusal_names_what_it_refuses_and_writes_nothing(tmp_path):
    image = tmp_path / "in.iso"
    image.write_bytes(_xiso.image({"default.xbe": b"XBEH", "gamedata/a.xbr": b"A"}))
    (colon := tmp_path / "colon.iso").write_bytes(_xiso.image({"x:y.xbr": b"A"}))
    (full := tmp_path / "full").mkdir()
    (full / "mine.txt").write_text("mine", encoding="utf-8")
    (tree := tmp_path / "tree" / "gamedata").mkdir(parents=True)
    (tree / "new.xbr").write_bytes(b"xobx")
    xbr = tmp_path / "x.xbr"
    xbr.write_bytes(b"xobx")
    out = str(tmp_path / "out")
    cases = [
        (tools.entity_list(str(tmp_path / "nope.xbr")), "no file"),
        (tools.entity_get(str(image), "golem"), "no gamedata/config.xbr"),
        (tools.xbr_edit(str(xbr), str(xbr), [{"op": "set"}]), "input"),
        (tools.xbr_edit(str(xbr), out, [{"op": "set", "file": "gamedata/config.xbr"}]), "the file is inp"),
        (tools.xbr_edit(str(xbr), out, [{"op": "set", "table": "t", "entity": "e", "prop": "p", "value": math.nan}]),
         "value"),
        (tools.pack_list(category="nope"), "nope"),
        (tools.pack_list(pack="nope"), "nope"),
        (tools.pack_build_iso(str(image), out, enable=["nope"]), "nope"),
        (tools.pack_build_iso(str(image), out, params={"player_max_hp": {"starting_hp": 500}}), "player_max_hp"),
        (tools.pack_build_iso(str(image), out, ["player_physics"], {"player_physics": {"gravity": True}}),
         "player_physics"),
        (tools.pack_build_iso(str(image), out), "not the vanilla"),   # D27
        (tools.rando_build_iso(str(image), out, 1, {"no_gemz": True}), "no_gemz"),
        (tools.rando_build_iso(str(image), out, 1, {"spoiler": str(image)}), "input"),   # D36
        (tools.rando_build_iso(str(image), out, 1, {"spoiler": out}), "output image itself"),
        (tools.iso_extract(str(image), str(full)), "not a missing or empty folder"),
        (tools.iso_extract(str(image), out, ["gamedata/b.xbr"]), "gamedata/b.xbr"),
        (tools.iso_extract(str(colon), out), "x:y.xbr"),   # AZ-216
        (tools.iso_repack(str(tree.parent), str(tree / "out.iso")), "inside src"),
        (tools.iso_repack(str(tree.parent), out, "usa"), "not files of the vanilla USA image: gamedata/new.xbr"),
    ]
    for reply, needle in cases:
        assert not reply["success"] and needle in reply["error"], (needle, reply)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == [
        "colon.iso", "full/mine.txt", "in.iso", "tree/gamedata/new.xbr", "x.xbr"]
