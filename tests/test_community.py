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


DRIVE = r"""
const { content, needs } = await import(process.argv[2]);
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
               put: async (entries) => entries.forEach(([k, v]) => store.set(k, v)) };
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
console.log(JSON.stringify(out));
"""


@pytest.mark.web
def test_the_pages_content_install_fetches_each_entry_once_keeps_nothing_it_refuses_and_drops_what_an_update_drops(
        tmp_path):
    """web/content.mjs, the one Install path of the page's community tabs
    (driven on Node with the browser's parts stubbed): an entry and those it
    requires (a diamond) fetched once each, required first, ``k of n``
    heard as each file comes; an Update fetches only what changed and drops
    the files its new version doesn't hold; an engine refusal, an Install
    past MAX_ENTRY (refused before any fetch) and a reply past its listed
    size keep nothing; the requires walk names a cycle and an unknown id."""
    driver = tmp_path / "drive.mjs"
    driver.write_text(DRIVE, encoding="utf-8")
    module = (ROOT / "web" / "content.mjs").as_uri()
    done = subprocess.run(["node", str(driver), module], capture_output=True, text=True, timeout=60, check=False)
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
    assert out["liar"] == "packs/liar/pack.json: 4 bytes or more, past the community list's 2"
    assert out["untouched"] is True
    assert out["cycle"] == 'entry "x" requires itself (x -> y -> x)'
    assert out["unknown"] == 'no entry "z" in the community list'
