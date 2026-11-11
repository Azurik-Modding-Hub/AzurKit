"""Community packs (D988, ``tools.mods.community``): a pack.json is a mods
file of AzurKit's own packs and game-data edits, checked at Install and
again at each build; a recipe names one installed, untouched and pinned;
its built-in packs merge with the recipe's own, and its edits are a layer of
their own that a later layer may overwrite, reported (D28); and the page's
one Install path (``web/content.mjs``, on Node: ``web``). No game bytes:
fixture packs in a content repository made in ``tmp_path`` (D997: no pack
ships)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from azurkit import cli, sdk
from azurkit.core import gate
from azurkit.edits import preset, xbr
from azurkit.edits.layer import compose
from azurkit.tools.characters import content
from azurkit.tools.mods import community

GOLEM = {"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
         "prop": "hitPoints", "value": 321}
ROOT = Path(__file__).resolve().parent.parent
HARD = {"format": preset.FORMAT, "schema_version": 1, "layers": [
    {"tool": "mods", "kind": "packs", "recipe": {"enemy_scaling": {"enemy_damage_dealt_scale": 1.5},
                                                 "player_max_hp": {"starting_hp": 150}}},
    {"tool": "data", "kind": "xbr", "recipe": {"ops": [GOLEM]}}]}


def _pack(packs: dict | None = None, ops: list | None = None, **extra) -> dict:
    layers = ([{"tool": "mods", "kind": "packs", "recipe": packs}] if packs is not None else []) + (
        [{"tool": "data", "kind": "xbr", "recipe": {"ops": ops}}] if ops is not None else [])
    return {"format": preset.FORMAT, "schema_version": 1, "layers": layers, **extra}


def _repo(tmp_path, packs: dict[str, dict]) -> tuple[dict, callable]:
    """A content repository in ``tmp_path`` holding ``packs`` (id -> its
    pack.json), its manifest filled, and a fetch of its files."""
    repo = tmp_path / "repo"
    for name, doc in packs.items():
        (repo / community.PATH.format(name)).parent.mkdir(parents=True, exist_ok=True)
        (repo / community.PATH.format(name)).write_text(json.dumps(doc), encoding="utf-8")
    fetch = lambda path: (repo / path).read_bytes()   # noqa: E731
    entries = [{"id": name, "kind": "pack", "title": name, "author": "a tester", "licence": "MIT", "version": 1,
                "files": [{"path": community.PATH.format(name)}], "requires": []} for name in packs]
    return content.filled({"format": content.FORMAT, "schema_version": 1, "entries": entries}, fetch), fetch


def test_a_community_pack_is_a_mods_file_of_packs_and_game_data_edits_and_each_fault_refused_by_name():
    """A pack.json is a mods file of a ``mods`` packs layer and a ``data``
    xbr layer, release-free; its packs and operations normalize as a
    recipe's do (any finite value, D23) and carry the packs they need; the
    content folder's Install check of a pack entry is that check of its one
    file. Every fault is named, never a byte."""
    assert community.check(json.dumps(HARD)) == {
        "packs": {"player_max_hp": {"starting_hp": 150}, "enemy_scaling": {"enemy_damage_dealt_scale": 1.5}},
        "xbr": [GOLEM]}
    assert community.check(_pack({"qol_skip_logo": {}})) == {"packs": {"qol_skip_logo": {}}, "xbr": []}
    base = {"kind": "vanilla", "release": "usa", "iso_sha256": gate.USA.iso_sha256}
    for doc, why in [
        ("#p=AAAA", "pack.json: no JSON object"),
        ({"format": "azurik-custom-content", "schema_version": 1, "layers": []}, "format is not 'azurkit-preset'"),
        (_pack({"qol_skip_logo": {}}, base=base), "release-free: no base"),
        (_pack({"qol_skip_logo": {}}, result={}), "release-free: no result"),
        ({**_pack(), "layers": [{"tool": "randomizer", "kind": "plan", "recipe": {}}]},
         "no randomizer plan layer in a community pack (its: mods packs, data xbr): a randomizer's settings travel"),
        ({**_pack(), "layers": [{"tool": "characters", "kind": "characters", "recipe": {}}]},
         "a character travels as a community variant"),
        (_pack({"no_such_pack": {}}), "no pack 'no_such_pack'"),
        (_pack({"fps_unlock": {"target_fps": 1.5}}), "target_fps"),
        (_pack({"qol_memory_upper64_gpu": {}}), "needs 'qol_memory_upper64' in the same build: a community pack"),
        (_pack(ops=[{**GOLEM, "file": "default.xbe"}]), "xbr op 1 (set): file 'default.xbe' is no gamedata/"),
        ({**_pack(), "layers": [{"tool": "data", "kind": "xbr", "recipe": {"ops": [], "more": 1}}]}, "is {ops}"),
        (_pack({}, []), "sets a pack or a game-data value"),
    ]:
        with pytest.raises(ValueError, match="^pack.json: ") as caught:
            community.check(doc)
        assert why in str(caught.value), (doc, str(caught.value))
    entry = {"id": "hard", "kind": "pack", "files": [{"path": "packs/hard/pack.json"}]}
    assert community.refusal(entry, {"packs/hard/pack.json": json.dumps(HARD).encode()}) is None
    assert community.refusal({**entry, "kind": "variant"}, {}) is None   # a variant is builtin_refusal's
    assert community.refusal({**entry, "files": [*entry["files"], {"path": "packs/hard/x.bin"}]},
                             {}) == "a pack entry's one file is packs/hard/pack.json"
    assert community.refusal(entry, {"packs/hard/pack.json": json.dumps(_pack({"no": {}})).encode()}).startswith(
        "packs/hard/pack.json: no pack 'no'")


def test_a_recipes_community_pack_must_be_installed_untouched_and_pinned_and_set_its_packs_one_way(tmp_path):
    """A recipe's community pack resolves only from the content folder's
    install: not installed, pinned to another pack.json, or edited after its
    install is refused by name, saying what to Install or Update; its
    built-in packs then merge with the recipe's own, a pack set two ways
    refused naming both and the slider, equal copies one, nothing unticked."""
    soft = _pack({"enemy_scaling": {"enemy_damage_dealt_scale": 0.5}})
    manifest, fetch = _repo(tmp_path, {"hard": HARD, "soft": soft})
    root = tmp_path / "content"
    record = content.install(manifest, "hard", fetch, root)
    read = lambda path: (root / path).read_bytes()   # noqa: E731
    sha = hashlib.sha256(fetch(community.PATH.format("hard"))).hexdigest()
    [hard] = community.resolve([{"id": "hard", "sha": sha[:12]}], record, read)
    assert hard == {"id": "hard", "version": 1, "sha256": sha, **community.check(HARD)}
    for pins, why in [
        ([{"id": "soft"}], "community pack 'soft' isn't installed: Install it"),
        ([{"id": "hard", "sha": "0" * 12}], f"is pack.json {'0' * 12} there and {sha[:12]} here: Install or Update"),
        ([{"id": "hard"}, {"id": "hard"}], "community pack 'hard' is listed twice"),
        ([{"id": "Hard"}], "id 'Hard' is no lower-case identifier"),
        ({"id": "hard"}, "community is a list of {id, sha}"),
    ]:
        with pytest.raises(ValueError, match=".") as caught:
            community.resolve(pins, record, read)
        assert why in str(caught.value), (pins, str(caught.value))
    (root / community.PATH.format("hard")).write_text(json.dumps(_pack({"qol_skip_logo": {}})), encoding="utf-8")
    with pytest.raises(ValueError, match=r"pack.json is [0-9a-f]{12}, changed since its install"):
        community.resolve([{"id": "hard"}], record, read)

    own = {"qol_skip_logo": {}, "player_max_hp": {"starting_hp": 150}}
    assert community.merge(own, [hard]) == {"qol_skip_logo": {}, "player_max_hp": {"starting_hp": 150},
                                            "enemy_scaling": {"enemy_damage_dealt_scale": 1.5}}
    with pytest.raises(ValueError) as caught:
        community.merge({"player_max_hp": {"starting_hp": 2}}, [hard, {"id": "soft", **community.check(soft)}])
    assert str(caught.value) == ("player_max_hp's starting_hp: community pack hard sets 150, your packs 2: untick one; "
                                 "enemy_scaling's enemy_damage_dealt_scale: community pack soft sets 0.5, community "
                                 "pack hard 1.5: untick one")
    with pytest.raises(ValueError, match="community pack hard sets 150, your packs 200 \\(its default\\)"):
        community.merge({"player_max_hp": {}}, [hard])
    near = {"id": "near", **community.check(_pack({"enemy_scaling": {"enemy_damage_dealt_scale": 1.0000001},
                                                   "player_max_hp": {"starting_hp": 1234567}}))}
    with pytest.raises(ValueError) as caught:
        community.merge({"enemy_scaling": {"enemy_damage_dealt_scale": 1.0000002},
                         "player_max_hp": {"starting_hp": 1234568}}, [near])
    assert str(caught.value) == ("player_max_hp's starting_hp: community pack near sets 1234567, your packs 1234568: "
                                 "untick one; enemy_scaling's enemy_damage_dealt_scale: community pack near sets "
                                 "1.0000001, your packs 1.0000002: untick one")


def test_a_community_packs_edits_are_its_own_layer_a_later_edit_wins_and_its_build_carries_it():
    """A community pack's operations plan as its own layer, ``community
    <id>``, recording its id, version and pack.json's sha256, never its
    bytes; the player's own edit after it on the same bytes wins and the
    conflict names both (D28); one that can't apply is refused naming the
    pack. A build's manifest carries it back as a mods file's community
    layer, by id and sha12, which a link holds too."""
    base = {"gamedata/config.xbr": bytes(range(64))}
    sha = "ab" * 32
    ops = [{"op": "replace_bytes", "file": "gamedata/config.xbr", "offset": 16, "expected": bytes(range(16, 20)).hex(),
            "value": "01020304"}]
    pick = {"id": "hard", "version": 2, "sha256": sha, "packs": {}, "xbr": ops}
    made = community.layer(pick, gate.USA, base)
    assert (made.id, made.tool, made.kind, made.recipe) == ("community hard", "community", "packs",
                                                           {"id": "hard", "version": 2, "sha256": sha})
    mine = xbr.plan([{**ops[0], "value": "05060708"}], gate.USA, base)
    files, conflicts = compose(base, [made, mine])
    assert files["gamedata/config.xbr"][16:20] == bytes([5, 6, 7, 8])
    assert [(c.layer, c.overwrote) for c in conflicts] == [("data xbr", "community hard")]
    assert community.layer({**pick, "xbr": []}, gate.USA, base).changes == ()
    with pytest.raises(ValueError, match="^community pack 'hard': xbr op 1 \\(replace_bytes\\): .* not the bytes"):
        community.layer({**pick, "xbr": [{**ops[0], "offset": 0}]}, gate.USA, base)

    record = {"format": preset.MANIFEST, "result": {},
              "base": {"kind": "vanilla", "release": "usa", "iso_sha256": gate.USA.iso_sha256}, "layers": [
        {"tool": "mods", "kind": "packs", "recipe": {"pack": "qol_skip_logo", "params": {}}},
        {"tool": "community", "kind": "packs", "recipe": made.recipe},
        {"tool": "community", "kind": "packs", "recipe": {"id": "soft", "version": 1, "sha256": "cd" * 32}},
        {"tool": "data", "kind": "xbr", "recipe": {"ops": [GOLEM]}}]}
    found = preset.read(record)
    assert [(la["tool"], la["kind"]) for la in found["layers"]] == [("mods", "packs"), ("community", "packs"),
                                                                    ("data", "xbr")]
    assert found["layers"][1]["recipe"] == {"packs": [{"id": "hard", "sha": "ab" * 6}, {"id": "soft", "sha": "cd" * 6}]}
    assert preset.decode(preset.encode(found)) == found
    with pytest.raises(ValueError, match="not a 'packs' layer of tool 'community'"):
        preset.read({**record, "layers": [{"tool": "community", "kind": "packs", "recipe": {"id": "hard"}}]})


def _installed(tmp_path, monkeypatch, packs: dict[str, dict]) -> tuple[Path, dict]:
    """A folder source of ``packs``, the content folder empty under ``tmp_path``: the source and its manifest."""
    manifest, _ = _repo(tmp_path, packs)
    (tmp_path / "repo/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(content, "ROOT", tmp_path / "content")
    monkeypatch.delenv(sdk.SOURCE_ENV, raising=False)
    return tmp_path / "repo", manifest


def test_the_sdk_installs_lists_links_and_restores_a_community_pack_and_refuses_each_fault_by_name(tmp_path, monkeypatch):
    """The sdk's community packs (Step 4.3k): an Install of a pack.json that is no community pack writes nothing,
    on both Install paths; an installed one lists with its values and edits in words, never a ``replace_bytes``'s
    bytes; a link carries it by id and sha12, its packs merged, and is refused by name where it isn't installed or
    is at another sha; a recipe that sets one of its packs another way is refused by name; a remembered setup keeps
    it by id across an Update and drops an uninstalled one by name; ``azurkit content check`` reads a pack too."""
    bytes_op = {"op": "replace_bytes", "file": "gamedata/config.xbr", "offset": 16, "expected": "00010203",
                "value": "04050607"}
    bad = _pack({"qol_memory_upper64_gpu": {}})   # without the pack it requires
    source, manifest = _installed(tmp_path, monkeypatch, {"hard": HARD, "raw": _pack(None, [bytes_op]), "bad": bad})
    with pytest.raises(ValueError, match="bad: .*pack.json: pack 'qol_memory_upper64_gpu' needs 'qol_memory_upper64'"):
        sdk.content_install({"id": "bad", "source": str(source)})
    assert not (tmp_path / "content/packs/bad").exists() and sdk.community() == {"packs": []}
    fetched = {community.PATH.format("bad"): json.dumps(bad).encode()}
    with pytest.raises(ValueError, match="bad: .*needs 'qol_memory_upper64'"):
        sdk.content_check({"manifest": json.dumps(manifest), "id": "bad", "files": fetched})
    assert cli.main(["content", "check", str(source)]) == 1   # its one bad entry, named

    sdk.content_install({"id": "hard", "source": str(source)})
    sdk.content_install({"id": "raw", "source": str(source)})
    sha = hashlib.sha256(json.dumps(HARD).encode()).hexdigest()[:12]
    [hard, raw] = sdk.community()["packs"]
    assert hard == {"id": "hard", "version": 1, "sha": sha, "packs": community.check(HARD)["packs"],
                    "ops": ["gamedata/config.xbr: critters_damage / golem / hitPoints = 321"]}
    assert raw["ops"] == ["gamedata/config.xbr: 4 bytes at 0x10"]

    recipe = {"packs": {}, "community": [{"id": "hard"}]}
    found = sdk.preset_decode(sdk.preset_encode(recipe))
    by = {la["tool"]: la["recipe"] for la in found["layers"]}
    assert by["community"] == {"packs": [{"id": "hard", "sha": sha}]} and by["mods"] == community.check(HARD)["packs"]
    assert sdk.read_mods(sdk.mods_file({"recipe": recipe})["text"])["community"] == [{"id": "hard", "sha": sha}]
    with pytest.raises(ValueError, match="your packs 2: untick one"):
        sdk.preset_encode({"packs": {"player_max_hp": {"starting_hp": 2}}, "community": [{"id": "hard"}]})
    other = preset.encode(found | {"layers": [la if la["tool"] != "community" else {
        **la, "recipe": {"packs": [{"id": "hard", "sha": "0" * 12}]}} for la in found["layers"]]})
    with pytest.raises(ValueError, match="Install or Update it"):
        sdk.preset_decode(other)
    gone = preset.encode(found | {"layers": [la if la["tool"] != "community" else {
        **la, "recipe": {"packs": [{"id": "none"}]}} for la in found["layers"]]})
    with pytest.raises(ValueError, match="'none' isn't installed: Install it"):
        sdk.preset_decode(gone)

    back = sdk.restore({"community": [{"id": "hard"}, {"id": "none"}]})
    assert back["community"] == [{"id": "hard"}] and "'none' isn't installed" in back["dropped"][0]
    assert sdk.restore({"community": "hard"})["dropped"] == ["the community packs (not a list)"]
    (tmp_path / "content" / community.PATH.format("hard")).write_text("{}", encoding="utf-8")
    assert "changed since its install" in sdk.community()["packs"][0]["refused"]


@pytest.mark.parametrize("release", ["usa", pytest.param("europe", marks=pytest.mark.europe)])
@pytest.mark.vanilla
def test_a_community_pack_builds_its_packs_and_edits_as_its_own_layer_and_its_link_and_build_carry_it(
        release, request, tmp_path, monkeypatch):
    """A recipe's community pack builds the same game files as its packs and edits written out (the design's
    invariant, so no golden records one); its layer sits after the packs, before the player's own edits, whose set on
    its cell wins, reported (D28); ``azurkit build --community`` builds it; the build's recipe (its mods file) names
    it by id and sha12 and rebuilds the image."""
    image = str(request.getfixturevalue(f"{release}_iso"))
    source, _ = _installed(tmp_path, monkeypatch, {"hard": HARD})
    sdk.content_install({"id": "hard", "source": str(source)})
    sha = hashlib.sha256(json.dumps(HARD).encode()).hexdigest()[:12]
    picked = community.check(HARD)
    made, report = sdk.image({"iso": image, "packs": {}, "community": [{"id": "hard"}]})
    plain, expanded = sdk.image({"iso": image, "packs": picked["packs"], "xbr": picked["xbr"]})
    assert [la["id"] for la in report["layers"]] == ["pack player_max_hp", "pack enemy_scaling", "community hard"]
    assert report["result"] == expanded["result"] and report["conflicts"] == [] and made.size == plain.size

    _, mine = sdk.image({"iso": image, "packs": {}, "community": [{"id": "hard"}], "xbr": [{**GOLEM, "value": 322}]})
    assert [la["id"] for la in mine["layers"]][-2:] == ["community hard", "data xbr"]
    assert [c for c in mine["conflicts"] if "data xbr" in c and "community hard" in c]

    out = tmp_path / "built.iso"
    assert cli.main(["build", "--iso", image, "--out", str(out), "--no-defaults", "--community", "hard"]) == 0
    opened = sdk.open_build(str(out))
    by = {la["tool"]: la["recipe"] for la in opened["layers"]}
    assert by["community"] == {"packs": [{"id": "hard", "sha": sha}]}
    again = sdk.read_mods(json.dumps(opened)) | {"iso": image}
    assert sdk.image(again)[1]["result"] == report["result"]


DRIVE = r"""
const { content, later, needs } = await import(process.argv[2]);
const enc = (text) => new TextEncoder().encode(text);
const entry = (id, requires, files, version = 1) => ({ id, kind: "pack", title: id, version, requires,
  files: files.map(([path, text, size]) => ({ path, size: size ?? enc(text).length, sha256: `${path}@${version}` })) });
const list = (...entries) => ({ format: "azurik-custom-content", schema_version: 1, entries });
let bodies = {}, refuse = null;
const fetched = [], handed = [], heard = [], store = new Map();
const fetch = async (url) => {
  const path = new URL(url).pathname.replace("/content/", ""), text = bodies[path];
  fetched.push(path);
  if (text === undefined) return { ok: false, status: 404 };
  const data = enc(text);
  let at = 0;
  return { ok: true, status: 200, headers: { get: () => null }, text: async () => text,
           body: { getReader: () => ({ cancel: async () => {},
                                       read: async () => at >= data.length ? { done: true }
                                         : { done: false, value: data.slice(at, at += 4) } }) } };
};
const call = async (type, given) => {
  const manifest = JSON.parse(given.manifest);
  if (refuse) return { refused: refuse };
  return "id" in given ? { manifest, install: needs(new Map(manifest.entries.map((e) => [e.id, e])), given.id) }
                       : { manifest };
};
const kept = { get: async (key) => store.get(key),
               put: async (entries) => entries.forEach(([k, v]) => store.set(k, v)),
               change: async (keys, fn) => fn(keys.map((k) => store.get(k))).map((v, i) => store.set(keys[i], v) && v) };
const c = content({ call, app: false, fallback: "content/", kept, fetch,
                    handoff: (files) => handed.push(Object.keys(files)), storage: { getItem: () => null },
                    location: { href: "http://site.test/", origin: "http://site.test" } });
const out = {};
const tried = async (act) => { try { await act(); return null; } catch (error) { return error.message; } };
const picture = () => JSON.stringify([[...store.keys()], Object.keys(store.get("files") ?? {}),
                                      store.get("installed")]);
const progress = (k, n) => heard.push(`${k} of ${n}`);

const v1 = list(entry("a", ["b", "c"], [["packs/a/pack.json", "a1"], ["packs/a/old.json", "o"]]),
                entry("b", ["d"], [["packs/b/pack.json", "bb"]]), entry("c", ["d"], [["packs/c/pack.json", "cc"]]),
                entry("d", [], [["packs/d/pack.json", "dd"]]));
bodies = { "manifest.json": JSON.stringify(v1), "packs/a/pack.json": "a1", "packs/a/old.json": "o",
           "packs/b/pack.json": "bb", "packs/c/pack.json": "cc", "packs/d/pack.json": "dd" };
await c.read();
fetched.length = 0;
await c.install(c.state.manifest.entries[0], progress);
out.diamond = { fetched: [...fetched], heard: [...heard], kept: Object.keys(store.get("files")).sort(),
                installed: Object.keys(store.get("installed")).sort(), handed: handed.length };

const v2 = list({ ...v1.entries[0], version: 2, files: [{ path: "packs/a/pack.json", size: 2, sha256: "a@2" }] },
                ...v1.entries.slice(1));
bodies["manifest.json"] = JSON.stringify(v2);
bodies["packs/a/pack.json"] = "a2";
await c.read();
out.states = c.state.entries.map((e) => `${e.id} ${e.state}`);
fetched.length = heard.length = 0;
await c.install(c.state.entries[0], progress);
out.update = { fetched: [...fetched], heard: [...heard], kept: Object.keys(store.get("files")).sort(),
               a: new TextDecoder().decode(store.get("files")["packs/a/pack.json"]),
               version: store.get("installed").a.version, states: c.state.entries.map((e) => `${e.id} ${e.state}`) };

const before = picture(), handedBefore = handed.length;
refuse = "a: packs/a/pack.json's sha256 0123456789ab isn't the manifest's 0123456789ac";
out.refused = await tried(() => c.install(c.state.entries[0]));
refuse = null;
bodies["manifest.json"] = JSON.stringify(list(...v2.entries,
                                              entry("big", [], [["packs/big/pack.json", "", 2 ** 28 + 1]]),
                                              entry("liar", [], [["packs/liar/pack.json", "", 2]])));
bodies["packs/liar/pack.json"] = "ten bytes!";
await c.read();
fetched.length = 0;
out.big = await tried(() => c.install(c.state.manifest.entries.find((e) => e.id === "big")));
out.bigFetched = fetched.length;
out.liar = await tried(() => c.install(c.state.manifest.entries.find((e) => e.id === "liar")));
out.untouched = picture() === before && handed.length === handedBefore;
out.cycle = await tried(() => needs(new Map([["x", { requires: ["y"] }], ["y", { requires: ["x"] }]]), "x"));
out.unknown = await tried(() => needs(new Map([["x", { requires: ["z"] }]]), "x"));

const m1 = list(entry("e", [], [["packs/e/pack.json", "e1"], ["packs/shared.json", "s1"]]),
                entry("f", [], [["packs/f/pack.json", "f1"]]));
const m2 = list(entry("e", [], [["packs/e/pack.json", "e2"]], 2),
                entry("f", [], [["packs/f/pack.json", "f2"], ["packs/shared.json", "s2"]], 2));
Object.assign(bodies, { "manifest.json": JSON.stringify(m1), "packs/e/pack.json": "e1", "packs/shared.json": "s1",
                        "packs/f/pack.json": "f1" });
await c.read();
for (const id of ["e", "f"]) await c.install(c.state.manifest.entries.find((e) => e.id === id));
Object.assign(bodies, { "manifest.json": JSON.stringify(m2), "packs/e/pack.json": "e2", "packs/shared.json": "s2",
                        "packs/f/pack.json": "f2" });
await c.read();
for (const id of ["f", "e"]) await c.install(c.state.manifest.entries.find((e) => e.id === id));
out.moved = { f: Object.keys(store.get("installed").f.files).sort(),
              shared: new TextDecoder().decode(store.get("files")["packs/shared.json"] ?? new Uint8Array()),
              handed: handed.at(-1).includes("packs/shared.json") };

const part = "variants/v/shipped/parts/p.azkp";   // a built-in's shipped Check part: left for the Check that asks
Object.assign(bodies, { "manifest.json": JSON.stringify(list(entry("v", [], [["variants/v/v.md", "v"], [part, "p"]]))),
                        "variants/v/v.md": "v", [part]: "p" });
await c.read();
fetched.length = 0;
await c.install(c.state.manifest.entries[0]);
out.later = { fetched: [...fetched], kept: Object.keys(store.get("files")).filter((p) => p.startsWith("variants/")),
              listed: Object.keys(store.get("installed").v.files).sort(), handed: handed.at(-1).includes(part),
              rule: JSON.parse(process.argv[3]).map(later) };
console.log(JSON.stringify(out));
"""


@pytest.mark.web
def test_the_pages_content_install_fetches_each_entry_once_keeps_nothing_it_refuses_and_drops_what_an_update_drops(
        tmp_path):
    """web/content.mjs, the one Install path of the page's community tabs
    (driven on Node with the browser's parts stubbed): an entry and those it
    requires (a diamond) fetched once each, required first, ``k of n``
    heard as each file comes; an Update fetches only what changed and drops
    the files its new version doesn't hold, but not one another installed
    entry holds now (a file moved to it); an engine refusal, an Install
    past MAX_ENTRY (refused before any fetch) and a reply past its listed
    size keep nothing; the requires walk names a cycle and an unknown id. A built-in's shipped Check part is listed
    in its entry's record but left for the Check that asks for it (Step 4.6p: never fetched, kept or handed to the
    engine at a page start), by content.py's rule (``content.later``)."""
    from azurkit.tools.characters import content

    paths = ["variants/booblord/shipped/parts/85b8a79a6d8d5c18.azkp", "variants/booblord/shipped/usa-0123.azkp",
             "variants/booblord/shipped/parts/x/y.azkp", "clips/booblord/shipped/parts/a.glb", "variants/b/variant.json"]
    driver = tmp_path / "drive.mjs"
    driver.write_text(DRIVE, encoding="utf-8")
    module = (ROOT / "web" / "content.mjs").as_uri()
    done = subprocess.run(["node", str(driver), module, json.dumps(paths)], capture_output=True, text=True, timeout=60,
                          check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout)
    pack = "packs/{}/pack.json".format
    assert out["diamond"] == {"fetched": [pack("d"), pack("b"), pack("c"), pack("a"), "packs/a/old.json"],
                              "heard": [f"{k} of 5" for k in range(6)], "kept": sorted(
                                  ["packs/a/old.json", *map(pack, "abcd")]),
                              "installed": ["a", "b", "c", "d"], "handed": 1}
    assert out["states"] == ["a update", "b installed", "c installed", "d installed"]
    assert out["update"] == {"fetched": [pack("a")], "heard": ["0 of 1", "1 of 1"], "kept": sorted(map(pack, "abcd")),
                             "a": "a2", "version": 2, "states": ["a installed", "b installed", "c installed",
                                                                  "d installed"]}
    assert out["refused"] == "a: packs/a/pack.json's sha256 0123456789ab isn't the manifest's 0123456789ac"
    assert out["big"] == "its files are 268,435,457 bytes, past the 268,435,456 one Install fetches"
    assert out["bigFetched"] == 0
    assert out["liar"] == "packs/liar/pack.json: past the 2 bytes its manifest lists"
    assert out["untouched"] is True
    assert out["cycle"] == 'entry "x" requires itself (x -> y -> x)'
    assert out["unknown"] == 'no entry "z" in the community list'
    assert out["moved"] == {"f": ["packs/f/pack.json", "packs/shared.json"], "shared": "s2", "handed": True}
    assert out["later"] == {"fetched": ["variants/v/v.md"], "kept": ["variants/v/v.md"], "handed": False,
                            "listed": ["variants/v/shipped/parts/p.azkp", "variants/v/v.md"],
                            "rule": [content.later(path) for path in paths]}
    assert out["later"]["rule"] == [True, False, False, False, False]


NEWER = r"""
const { content } = await import(process.argv[2]);
const list = JSON.stringify({ format: "azurik-custom-content", schema_version: 1, entries: [
  { id: "a", kind: "pack", title: "a", version: 1, requires: [], files: [] },
  { id: "b", kind: "pack", title: "b", version: 3, requires: [], files: [] }] });
const store = new Map([["installed", { a: { version: 2, source: "content/", files: {} },
                                       b: { version: 2, source: "content/", files: {} } }]]);
const kept = { get: async (key) => store.get(key), put: async (kv) => kv.forEach(([k, v]) => store.set(k, v)) };
const fetched = [];
const fetch = async (url) => (fetched.push(new URL(url).pathname), { ok: true, status: 200, text: async () => list });
const c = content({ call: async (_, given) => ({ manifest: JSON.parse(given.manifest) }), app: false,
                    fallback: "content/", kept, fetch, storage: { getItem: () => null },
                    location: { href: "http://site.test/", origin: "http://site.test" } });
await c.read();
console.log(JSON.stringify([c.state.entries.map((e) => [e.id, e.state, e.installed]), fetched]));
"""


@pytest.mark.web
def test_the_pages_content_list_offers_no_update_below_the_version_installed(tmp_path):
    """web/content.mjs on Node: an entry installed at a newer version than
    the source lists (a source rolled back, or another one picked) is
    installed, as the engine's ``content.states`` says (no Update goes
    down, SEC-8), not offered as an "Update to" the engine refuses; an
    older one is still an update (Step 4.42c)."""
    driver = tmp_path / "newer.mjs"
    driver.write_text(NEWER, encoding="utf-8")
    done = subprocess.run(["node", str(driver), (ROOT / "web" / "content.mjs").as_uri()], capture_output=True,
                          text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert json.loads(done.stdout) == [[["a", "installed", 2], ["b", "update", 2]], ["/content/manifest.json"]]


STALLED = r"""
const { content } = await import(process.argv[2]);
const enc = (text) => new TextEncoder().encode(text);
const list = JSON.stringify({ format: "azurik-custom-content", schema_version: 1, entries: [
  { id: "s", kind: "pack", title: "s", version: 1, requires: [], files: [{ path: "packs/s/pack.json", size: 2,
                                                                          sha256: "s@1" }] }] });
let stall = true;
const asked = [], store = new Map();
const kept = { get: async (key) => store.get(key), put: async (kv) => kv.forEach(([k, v]) => store.set(k, v)),
               change: async (keys, fn) => fn(keys.map((k) => store.get(k))).map((v, i) => store.set(keys[i], v) && v) };
const fetch = (url, options) => {   // the file's reply never comes while it stalls: only its signal ends the wait
  const path = new URL(url).pathname;
  asked.push(path);
  if (path.endsWith("manifest.json")) return Promise.resolve({ ok: true, status: 200, text: async () => list });
  if (stall) return new Promise((_, no) => options.signal.addEventListener("abort", () => no(options.signal.reason)));
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => null }, arrayBuffer: async () => enc("ss") });
};
const seconds = [];
const c = content({ call: async (_, given) => ({ manifest: JSON.parse(given.manifest) }), app: false,
                    fallback: "content/", kept, fetch, storage: { getItem: () => null },
                    location: { href: "http://site.test/", origin: "http://site.test" },
                    timeout: (s) => (seconds.push(s), AbortSignal.timeout(5)) });
await c.read();
const out = {}, alive = setInterval(() => {}, 1000);   // Node's AbortSignal.timeout holds no loop open
try { await c.install(c.state.manifest.entries[0]); } catch (error) { out.stalled = error.message; }
clearInterval(alive);
out.after = [c.state.installing, store.has("files"), [...seconds]];
stall = false;
await c.install(c.state.manifest.entries[0]);
out.again = [new TextDecoder().decode(store.get("files")["packs/s/pack.json"]), c.state.entries[0].state, asked.length];
console.log(JSON.stringify(out));
"""


@pytest.mark.web
def test_the_pages_content_install_whose_file_never_answers_ends_in_its_time_and_frees_install(tmp_path):
    """web/content.mjs on Node: an Install whose file's reply never comes
    (a half-open connection, a proxy that stalls) ends once its time is up
    (a minute and a second each 50,000 bytes of its listed size, as the
    worker's part fetch), naming the file, with nothing kept and Install
    free, so the next Install fetches and keeps it (Step 4.42c)."""
    driver = tmp_path / "stalled.mjs"
    driver.write_text(STALLED, encoding="utf-8")
    done = subprocess.run(["node", str(driver), (ROOT / "web" / "content.mjs").as_uri()], capture_output=True,
                          text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert json.loads(done.stdout) == {"stalled": "packs/s/pack.json: no answer in 60 s",
                                       "after": [None, False, [60, 60]], "again": ["ss", "installed", 3]}


TWO_TABS = r"""
const { content } = await import(process.argv[2]);
const enc = (text) => new TextEncoder().encode(text);
const entry = (id, version) => ({ id, kind: "pack", title: id, version, requires: [],
  files: [{ path: `packs/${id}/pack.json`, size: 2, sha256: `${id}@${version}` }] });
let entries = [], held = null, began = null, letGo = null;
const store = new Map();   // the browser's one store, both tabs': change() is one transaction
const kept = { get: async (key) => store.get(key), put: async (kv) => kv.forEach(([k, v]) => store.set(k, v)),
               change: async (keys, fn) => fn(keys.map((k) => store.get(k))).map((v, i) => store.set(keys[i], v) && v) };
const fetch = async (url) => {   // a file's body is its id and version; the held one's waits until let go
  const path = new URL(url).pathname.replace("/content/", "");
  if (path === "manifest.json") {
    const list = JSON.stringify({ format: "azurik-custom-content", schema_version: 1, entries });
    return { ok: true, status: 200, text: async () => list };
  }
  if (path === held) await new Promise((done) => { letGo = done; began(); });
  const { id, version } = entries.find((e) => e.files[0].path === path);
  return { ok: true, status: 200, headers: { get: () => null }, arrayBuffer: async () => enc(`${id}${version}`) };
};
const tab = () => content({ call: async (_, given) => ({ manifest: JSON.parse(given.manifest) }), app: false,
                            fallback: "content/", kept, fetch, storage: { getItem: () => null },
                            location: { href: "http://site.test/", origin: "http://site.test" } });
const keptNow = () => [Object.fromEntries(Object.entries(store.get("installed")).map(([id, r]) => [id, r.version])),
                     Object.fromEntries(Object.entries(store.get("files"))
                       .map(([path, data]) => [path, new TextDecoder().decode(data)]))];
const out = {};
for (const update of [false, true]) {
  store.clear();
  entries = [entry("x", 1), entry("y", 1)];
  const a = tab(), b = tab();
  if (update) await b.read().then(() => b.install(b.state.manifest.entries[1]));   // y 1, installed before
  await a.read();
  held = "packs/x/pack.json";
  const fetching = new Promise((done) => { began = done; });
  const first = a.install(a.state.manifest.entries[0]);   // tab A installs x, its file held
  await fetching;
  if (update) entries = [entry("x", 1), entry("y", 2)];
  await b.read();
  await b.install(b.state.manifest.entries[1]);   // tab B installs y (or updates it to 2) meanwhile, to its end
  held = null;
  letGo();
  await first;
  out[update ? "updated" : "installed"] = keptNow();
}
console.log(JSON.stringify(out));
"""


@pytest.mark.web
def test_the_pages_content_install_keeps_an_entry_another_tab_installed_or_updated_meanwhile(tmp_path):
    """web/content.mjs on Node, two tabs of one browser (two ``content()`` over one store): an Install whose files come
    while another tab installs another entry, or updates one, to its end merges into what the store holds then, so
    both entries stay installed, the other at its new version and files. Written onto what it read before its fetch,
    it lost the other's Install, or put the Update's old version and files back (audit pass 2's F3)."""
    driver = tmp_path / "two_tabs.mjs"
    driver.write_text(TWO_TABS, encoding="utf-8")
    done = subprocess.run(["node", str(driver), (ROOT / "web" / "content.mjs").as_uri()], capture_output=True,
                          text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    files = "packs/{}/pack.json".format
    assert json.loads(done.stdout) == {"installed": [{"x": 1, "y": 1}, {files("x"): "x1", files("y"): "y1"}],
                                       "updated": [{"x": 1, "y": 2}, {files("x"): "x1", files("y"): "y2"}]}


OVERTAKEN = r"""
const { content } = await import(process.argv[2]);
const [GH, MINE] = process.argv.slice(3);
const list = JSON.stringify({ format: "azurik-custom-content", schema_version: 1, entries: [] });
let began, settle, status;   // GitHub's read: held until settled, then a 404 or no answer
const fetch = (url) => String(url).startsWith(GH)
  ? new Promise((done, no) => {
      settle = () => status ? done({ ok: false, status }) : no(new TypeError("Failed to fetch"));
      began();
    })
  : Promise.resolve({ ok: true, status: 200, text: async () => list });
const store = new Map();
const kept = { get: async (key) => store.get(key), put: async (kv) => kv.forEach(([k, v]) => store.set(k, v)) };
const c = content({ call: async (_, given) => ({ manifest: JSON.parse(given.manifest) }), app: false, fallback: GH,
                    kept, fetch, storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
                    location: { href: "https://site.example.test/", origin: "https://site.example.test" } });
const out = [];
for (const [code, overtaken] of [[0, true], [404, true], [0, false]]) {
  status = code;
  const asked = new Promise((done) => { began = done; });
  const first = c.source(null);   // GitHub's, slow
  await asked;
  if (overtaken) await c.source(MINE);   // the player's own, read meanwhile
  settle();
  await first;
  out.push([c.state.source, c.state.why, !!c.state.manifest]);
}
console.log(JSON.stringify(out));
"""


@pytest.mark.web
def test_the_pages_content_read_the_player_overtook_says_nothing_when_it_fails_late(tmp_path):
    """web/content.mjs on Node: GitHub's read of the list, slow and then
    failing (no answer, or a 404) after the player's own source was read,
    drops its failure as a later read drops its answer, so the page doesn't
    say it couldn't reach the player's repository over the list it just read
    from it; a read that fails while its source is still the one set says so."""
    driver = tmp_path / "overtaken.mjs"
    driver.write_text(OVERTAKEN, encoding="utf-8")
    gh, mine = "https://github.example.test/content/", "https://mine.example.test/"
    done = subprocess.run(["node", str(driver), (ROOT / "web" / "content.mjs").as_uri(), gh, mine],
                          capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert json.loads(done.stdout) == [[mine, None, True], [mine, None, True], [
        gh, f"Couldn't reach the community list at {gh} (no answer: offline, or it doesn't let other sites read it).",
        True]]
