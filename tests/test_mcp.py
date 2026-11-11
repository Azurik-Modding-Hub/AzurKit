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
        (tools.pack_build_iso(str(image), out, config_mod={"format": "azurkit-preset", "schema_version": 1, "layers": [
            {"tool": "files", "kind": "put", "recipe": {"files": [
                {"path": "gamedata/config.xbr", "sha256": "ab" * 32, "size": 10}]}}]}), "files layer"),   # D35
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


def test_iso_repack_writes_no_image_beside_the_vanilla_ones(tmp_path, monkeypatch):
    """Step 4.42d: iso_repack keeps D36's folder rule as sdk.build and sdk.save do (gate.require_new_output): an
    out in the iso folder that holds the vanilla image is refused by name before anything is read or written (it
    checked only that out wasn't the image itself)."""
    (folder := tmp_path / "iso").mkdir()
    (folder / "usa.iso").write_bytes(b"not read")
    monkeypatch.setenv("AZURKIT_ISO", str(folder / "usa.iso"))
    monkeypatch.setenv("AZURKIT_ISO_EUROPE", str(tmp_path / "none.iso"))
    (tree := tmp_path / "tree").mkdir()
    reply = tools.iso_repack(str(tree), str(folder / "x.iso"))
    assert not reply["success"] and "which holds only the vanilla image" in reply["error"], reply
    assert sorted(p.name for p in folder.iterdir()) == ["usa.iso"]


def test_a_spoiler_naming_the_built_image_by_another_spelling_is_refused(tmp_path, monkeypatch):
    """Step 4.42d: rando_build_iso's spoiler is checked against the built image by file identity, so out spelled
    in another letter case (a case-blind disk) or through macOS's /System/Volumes/Data firmlink is refused and no
    image is left (D35), where the spoiler replaced the image and the reply still said success. One rule on every
    OS: a spelling that names out is refused, one that names another file gets the spoiler beside the image, and
    one whose folder is missing (the firmlink spelling off macOS) is not asked."""
    def build(made, out):   # sdk.build's report, its image a stand-in (the guards under test are the tool's)
        Path(out).write_bytes(b"image")
        return {"out": str(out), "release": "usa", "sha256": "0" * 64, "layers": [], "result": {}, "size": 5,
                "conflicts": [], "notes": [], "spoiler": "the spoiler"}

    monkeypatch.setattr(tools, "_recipe", lambda *args: ({"packs": {}}, []))
    monkeypatch.setattr(tools.sdk, "build", build)
    for n, spelled in enumerate((lambda out: out.with_name("BUILD.ISO"),
                                 lambda out: Path("/System/Volumes/Data" + str(out.resolve())))):
        (folder := tmp_path / str(n)).mkdir()
        out = folder / "build.iso"
        out.write_bytes(b"")
        aliased = (spoiler := spelled(out)).exists()
        out.unlink()
        if not aliased and not spoiler.parent.is_dir():
            continue   # off macOS the firmlink spelling names no folder: nothing to write there
        reply = tools.rando_build_iso(str(tmp_path / "in.iso"), str(out), 1, {"spoiler": str(spoiler)})
        if aliased:
            assert not reply["success"] and "output image itself" in reply["error"], reply
            assert list(folder.iterdir()) == []
        else:
            assert reply["success"], reply
            assert (out.read_bytes(), spoiler.read_text(encoding="utf-8")) == (b"image", "the spoiler")


# --- Step 4.28f: Modkit's unpinned MCP behaviours, ported -------------------------------------------------------


def test_pack_list_gives_each_pack_its_sliders_with_advisory_ranges_and_an_xbr_sliders_cell():
    """pack_list absorbed pack_sliders and pack_detail's XBR target cells
    (Modkit's Step MCP-1): every pack carries its category and sliders,
    whose ranges are advisory metadata (min and max, D23), an XBR slider
    names the cell it writes, and each pack names its releases."""
    packs = ok(tools.pack_list())
    sliders = [s for p in packs for s in p["sliders"]]
    assert sliders and all({"min", "max"} <= set(s) for s in sliders) and all("category" in p for p in packs)
    [hp] = ok(tools.pack_list(pack="player_max_hp"))
    assert [(s["name"], s["xbr"]) for s in hp["sliders"]] == [
        (name, {"file": "gamedata/config.xbr", "table": "settings_foo", "entity": entity, "prop": "Value"})
        for name, entity in (("starting_hp", "initial hp"), ("health_bar_full_scale", "max hp"))]
    assert hp["releases"] == ["usa", "europe"]


def test_xbr_edit_takes_the_mods_files_wire_format_and_an_unmet_expected_or_a_bool_writes_nothing(tmp_path):
    """Modkit's Step MCP-1 bug 8: xbr_edit spoke its own op dialect. It takes
    the mods file's xbr operations (``azurkit.edits.xbr``): a replace whose
    bytes hold what it ``expected`` applies, while an unmet ``expected`` or
    a bool value fails the call with nothing written."""
    src, out = tmp_path / "config.xbr", tmp_path / "out.xbr"
    src.write_bytes(b"xobx" + bytes(60))
    replaced = tools.xbr_edit(str(src), str(out), [{"op": "replace_bytes", "offset": 4, "value": "0102",
                                                    "expected": "0000"}])
    assert ok(replaced)["ops_applied"] == 1 and out.read_bytes() == b"xobx\x01\x02" + bytes(58)
    out.unlink()
    refused = [tools.xbr_edit(str(src), str(out), [op]) for op in (
        {"op": "replace_bytes", "offset": 0, "value": "00", "expected": "ff"},
        {"op": "set", "table": "armor_properties", "entity": "no_armor_1", "prop": "Level", "value": True})]
    assert not refused[0]["success"] and refused[0]["error"].startswith("xbr op 1 (replace_bytes): ")
    assert refused[0]["error"].endswith(" at 0x0, not the bytes it expects")
    # The whole reason: on this stand-in file a set fails whatever its value.
    assert (refused[1]["success"], refused[1]["error"]) == (
        False, "xbr op 1 (set): value: True is not a finite number")
    assert not out.exists() and src.read_bytes() == b"xobx" + bytes(60)


def test_pack_build_iso_builds_a_config_mod_alone_and_with_neither_has_nothing_to_build(usa_iso, tmp_path):
    """Modkit's Step MCP-1 bug 14: an empty ``enable`` was refused, so a
    build with only a ``config_mod`` was impossible over MCP. It builds,
    changing config.xbr alone (and filelist.txt, which lists each file's
    md5, as every build does); with neither, and the packs on by default
    left out (D528), there is nothing to build and the call fails, nothing
    written."""
    off = [p["name"] for p in ok(tools.pack_list()) if p["default_on"]]
    mod = json.dumps({"_keyed_patches": {"settings_foo": {"initial fuel": {"Value": 75.0}}}})   # Modkit's format
    built = ok(tools.pack_build_iso(str(usa_iso), str(tmp_path / "mod.iso"), [], config_mod=mod, disable=off))
    assert (built["summary"]["packs_applied"], built["summary"]["files_changed"]) == (
        [], ["filelist.txt", "gamedata/config.xbr"])
    Path(built["output_path"]).unlink()
    empty = tools.pack_build_iso(str(usa_iso), str(tmp_path / "none.iso"), [], disable=off)
    assert (empty["success"], empty["error"]) == (False, "nothing to build: no pack is enabled and there is no "
                                                         "config_mod")
    assert list(tmp_path.iterdir()) == []
