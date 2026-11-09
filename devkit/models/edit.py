"""One verb from the vanilla body to a built image through Blender (Modkit's
Step 2.158, D465: ``python -m devkit models model edit``).

:func:`prepare` makes or reopens a work folder ``DIR`` (outside the
checkout and the images' folders: everything in it is a game asset):

- ``DIR/model_edit.json`` stamps it (the image's release and its
  characters.xbr's sha256, the body, the variant's name, the import);
  a folder stamped for another body or image is refused.
- ``DIR/export/`` is ``model export`` of the vanilla body, with only the
  clips ``clips`` names (none by default), made once.
- ``DIR/job.json`` is the Blender session's job
  (:mod:`devkit.models.blender.edit_session`): it imports the export
  (or reopens ``DIR/edit.blend``), and every save writes ``DIR/edit.glb``
  (what is seen, modifiers applied, every action) and then
  ``DIR/edit.json``'s save count.
- The recipe: ``DIR/recipe.json`` once a pass has written it; before
  that the ``seed`` (a ``--variant-file``'s recipe, never written, with
  the files it names copied from beside it, or a built-in's with its
  WAVs and clip files copied beside it), else
  ``{"base": SPECIES, "mode": "own"}``.
- ``bake``: what a player build of the species in the recipe's mode adds
  to the body's own load runs (the clips it bakes onto it), measured once
  on the vanilla body, so a pass weighs the body as the build will.

:func:`run` starts Blender: interactive (the owner's own Blender and
preferences, no ``--background``; refused when ``$CLAUDECODE`` or
``$PYTEST_CURRENT_TEST`` is set, so an agent or a test never opens a
window) or headless (``--background --factory-startup``, the job's
``--script`` run after the import, one save, then quit; a script that
raises, or a run that saves nothing, is refused by name), once one of the
machine's Blender slots is free (``blender.batch.slot``).  It watches
``DIR/edit.json``: each new save count runs :func:`run_pass` once on the
newest ``edit.glb`` (saves made during a pass are one), until Blender
exits.  A pass:

- reads the save as the recipe's ``mesh.gltf`` (``import`` topology, or
  weights) with the recipe's ``ops`` after it, as W24 does, onto the
  vanilla body (:func:`~azurkit.tools.characters.mesh_edit.plan`), and its
  animations as clips (:func:`~azurkit.tools.characters.clip_import.read_clips`,
  thinned, each refused past its tolerance), into
  ``DIR/pass-<k>/characters.xbr`` and ``index.xbr``, but an animation of one
  of the body's own clips that no recipe column plays: a build stores a
  recipe clip as ``v/<name>``, which only a column plays, so that edit
  would play nowhere; it is named and left out;
- runs ``model preview`` into ``DIR/previews/<k>/`` (unless ``preview``
  is off) and ``model inspect``'s report (the game's budget, with
  ``bake``) on the body as a build leaves its LODs (Step 2.166e): worn by
  the player (W1's ``body`` cell), with the LODs W39 cuts from the pass's
  LOD 0 and the switch distances it sets
  (:func:`~azurkit.tools.characters._player_character.write_lods`, the
  recipe's ``lods``, or a body's own LODs at their vanilla shares; Step
  2.166d) and the shadow LOD W36 cuts where the build would
  (:func:`~azurkit.tools.characters._player_character.write_shadow_lod`, the
  recipe's ``lods.shadow``; cut from the pass's LOD 0, in a worker while
  Blender draws), each LOD's row printed as ``model inspect`` prints it,
  inside the swap's build state on the session's image (``ports.building``:
  the packs a build reads, for the lines);
- writes ``DIR/recipe.json`` (read again first, with any edit made to
  it since the last pass): ``mesh.gltf`` {``file`` ``edit.glb``,
  ``sha256``, ``import``} and, for each animation, ``clips.<name>``'s
  ``generator`` ``gltf``, ``file``, ``sha256`` and ``animation``, every
  other key as it was (``box``, ``active``, ``rate``, ``columns``);
- appends one ``DIR/log.jsonl`` row (sha256, counts, budget, problems,
  or the refusal).  A refused pass writes no recipe and the watch goes
  on.

:func:`build` makes ``OUT.iso`` with the sdk's build (``sdk.build``) from
the same release's vanilla image, the packs on by default for the
session's ``ram`` and the character ``DIR/recipe.json``'s variant (its
``variant_file``), only when the last pass passed (D27, D35, D36).
Nothing here prints a byte or a coordinate."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from azurkit.tools.characters.model_inspect import DEFAULT_RAM
from devkit.models import image

STAMP = "model_edit.json"
RECIPE = "recipe.json"
LOG = "log.jsonl"
SAVED = "edit.glb"
SAVES = "edit.json"
BLEND = "edit.blend"
POLL = 0.5
"""Seconds between looks at ``DIR/edit.json`` while Blender runs."""
TIMEOUT = 1800
"""Seconds a headless Blender may take."""
AGENT_ENV = ("CLAUDECODE", "PYTEST_CURRENT_TEST")
"""Set by an agent's shell or a test run: the interactive mode refuses to
start under either (no window an agent or a test opens)."""


@dataclass
class Session:
    """A work folder ready for Blender (:func:`prepare`)."""

    work: Path
    iso: Path
    body: str
    species: str
    name: str
    mode: str
    export: Path
    characters: bytes
    config: bytes
    index: bytes
    recipe: dict
    passes: int = 0
    last_ok: bool | None = None
    bake: int = 0
    ram: int = DEFAULT_RAM
    """The machine's MiB the passes and ``--build`` are for (``--ram``, Step
    2.162i; 128 by default since D588): each pass weighed against its
    lines, ``--build`` made for that machine on the default packs."""


def _seed(name: str, species: str, variant_file: Path | None, builtin: str | None, work: Path) -> dict:
    """The recipe a new work folder starts from (module docstring)."""
    from azurkit.tools.characters import _player_variants as variants

    if variant_file is not None:
        doc = json.loads(Path(variant_file).read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or name not in doc or not isinstance(doc[name], dict):
            raise ValueError(f"--variant-file {variant_file}: it has no recipe {name!r}")
        recipe = doc[name]
        for file in _named_files(recipe):   # its files, beside the recipe now
            src, rel = Path(variant_file).parent / file, Path(file)
            if src.is_file() and not rel.is_absolute() and ".." not in rel.parts:
                (work / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, work / rel)
    elif builtin is not None:
        doc = json.loads(variants.BUILTIN.read_text(encoding="utf-8"))
        if builtin not in doc:
            raise ValueError(f"--from {builtin!r}: no built-in variant has that name ({', '.join(sorted(doc))})")
        recipe, parent = variants.recipe_of(doc, builtin, "built-in")   # one from another as it builds (Step 2.177)
        recipe = variants.own_recipe(recipe)   # a weapon over its moves left out (Step 2.209)
        for folder in (variants.SOUNDS / (parent or builtin), variants.CLIPS / (parent or builtin)):   # its files
            for f in sorted(folder.glob("*")) if folder.is_dir() else ():
                if f.is_file() and f.suffix.lower() in (".wav", ".glb", ".gltf", ".bin"):
                    shutil.copy2(f, work / f.name)
    else:
        recipe = {"base": species, "mode": "own"}
    return json.loads(json.dumps(recipe))


def _named_files(node) -> list[str]:
    """Every file a recipe names (``file``, ``files`` and ``wavs``' lists,
    at any depth), read beside it."""
    if isinstance(node, list):
        return [f for x in node for f in _named_files(x)]
    if not isinstance(node, dict):
        return []
    out = []
    for k, v in node.items():
        if k == "file" and isinstance(v, str):
            out.append(v)
        elif k == "files" and isinstance(v, list):
            out += [f for f in v if isinstance(f, str)]
        elif k == "wavs" and isinstance(v, dict):
            out += [f for fs in v.values() if isinstance(fs, list) for f in fs if isinstance(f, str)]
        else:
            out += _named_files(v)
    return out


def _bake(iso: Path, body: str, species: str, mode: str) -> int:
    """Bytes a player build of ``species`` in ``mode`` adds to ``body``'s
    own load runs (:func:`~azurkit.tools.characters.model_inspect.own_runs`):
    the clips it bakes onto the vanilla body (the swap's own dress,
    ``tools.characters.dressed``, on the image's vanilla files alone)."""
    from azurkit.tools import characters, mods
    from azurkit.tools.characters import ports
    from azurkit.tools.characters._player_character import DEFAULT_MODE, MODES
    from azurkit.tools.characters.model_inspect import own_runs

    stamp = image.stamp(iso)
    vanilla = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    before = own_runs(vanilla.read(characters.FILES[0]), body)["bytes"]
    game, *_ = characters.dressed({"species": species, "mode": mode if mode in MODES else DEFAULT_MODE}, vanilla, (),
                                  characters.packs_view(stamp.release, mods.PACKS))
    return max(0, own_runs(bytes(game["characters.xbr"]), body)["bytes"] - before)


@contextlib.contextmanager
def _building(iso: Path):
    """The swap's build state on the vanilla image ``iso`` (D27), the packs
    as a build reads them: what W36, W39 and ``model_inspect``'s lines read
    outside a build."""
    from azurkit.tools import characters, mods
    from azurkit.tools.characters import ports

    stamp = image.stamp(iso)
    with ports.building(ports.Build(ports.Vanilla(stamp.release, stamp.path, stamped=stamp),
                                    packs=characters.packs_view(stamp.release, mods.PACKS))):
        yield


def prepare(body_name: str, work: Path, *, iso: Path | None = None, name: str | None = None,
            variant_file: Path | None = None, builtin: str | None = None, base: str | None = None,
            weights: bool = False, clips: tuple[str, ...] = ()) -> Session:
    """The work folder ``work`` for editing ``body_name`` (a body or a
    species) made or reopened (module docstring); :class:`ValueError`
    names what refuses it, before anything is written but the folder."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import gltf

    iso = Path(image.find(str(iso) if iso else None)).absolute()
    characters, config, index = image.read(iso, "gamedata/characters.xbr", "gamedata/config.xbr",
                                           "gamedata/index/index.xbr")
    if not gltf.vanilla_characters(characters):
        raise ValueError(f"{iso}'s characters.xbr isn't vanilla: an edit is made onto vanilla (D27)")
    body, species = gltf.resolve_body(characters, config, body_name)
    species = base or species
    if species is None:
        raise ValueError(f"{body_name!r} is a body: give --base SPECIES (a species that wears it)")
    if variant_file is not None and builtin is not None:
        raise ValueError("--variant-file and --from both seed the recipe: give one")
    if variant_file is not None and name is None:
        doc = json.loads(Path(variant_file).read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or len(doc) != 1:
            raise ValueError(f"--variant-file {variant_file}: give --variant NAME (it holds {len(doc)} recipes)")
        name = next(iter(doc))
    name = name or f"{species}_edit"
    if name in variants.builtins():
        raise ValueError(f"--variant {name!r}: a built-in variant has that name; give another")
    stamp = {"region": image.stamp(iso).release.name, "characters_sha256": hashlib.sha256(characters).hexdigest(),
             "body": body, "variant": name, "import": "weights" if weights else "topology",
             "clips": sorted(clips)}
    # a model edit's own folder may be reopened, so not the emptiness check: what it holds is read below
    work = image.output(work, iso, file=True, flag="--work")
    if (work / STAMP).is_file():
        old = json.loads((work / STAMP).read_text(encoding="utf-8"))
        changed = [k for k in ("region", "characters_sha256", "body", "variant", "import")
                   if old.get(k) != stamp[k]]
        if changed:
            raise ValueError(f"--work {work} is a model-edit folder for another {', '.join(changed)}: give a new "
                             "folder")
        stamp["clips"] = old.get("clips", [])
    elif work.exists() and (not work.is_dir() or any(work.iterdir())):
        raise ValueError(f"--work {work} already holds something that isn't a model-edit folder; give a new or "
                         "empty folder")
    export = work / "export"
    if not export.is_dir():
        work.mkdir(parents=True, exist_ok=True)
        gltf.export_body(characters, body, export, list(stamp["clips"]), protect=(iso,))
    gltf_file = next(export.glob("*.gltf"))
    if (work / RECIPE).is_file():
        recipe = json.loads((work / RECIPE).read_text(encoding="utf-8"))[name]
    else:
        recipe = _seed(name, species, variant_file, builtin, work)
    (work / STAMP).write_text(json.dumps(stamp, indent=1), encoding="utf-8")
    rows = (work / LOG).read_text(encoding="utf-8").splitlines() if (work / LOG).is_file() else []
    return Session(work, iso, body, species, name, stamp["import"], gltf_file, characters, config, index, recipe,
                   len(rows), json.loads(rows[-1]).get("ok") if rows else None,
                   _bake(iso, body, species, str(recipe.get("mode", ""))))


def _job(s: Session, script: Path | None, headless: bool) -> Path:
    job = s.work / "job.json"
    job.write_text(json.dumps({"export": str(s.export), "blend": str(s.work / BLEND), "glb": str(s.work / SAVED),
                               "saves": str(s.work / SAVES), "script": str(script) if script else None,
                               "headless": headless}), encoding="utf-8")
    return job


def _saves(s: Session) -> int:
    try:
        return int(json.loads((s.work / SAVES).read_text(encoding="utf-8"))["n"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def check_mode(headless: bool, script: Path | None = None) -> None:
    """Refuse the interactive mode under :data:`AGENT_ENV`, and a
    ``script`` without ``headless`` or that isn't there (before anything
    is written or started)."""
    if not headless and any(os.environ.get(k) for k in AGENT_ENV):
        raise ValueError("an agent or a test runs model edit --headless: the interactive mode opens Blender's "
                         "window, which is the owner's")
    if script is not None and not headless:
        raise ValueError("--script runs in the headless mode only (give --headless)")
    if script is not None and not Path(script).is_file():
        raise ValueError(f"--script {script}: no such file")


def run(s: Session, *, headless: bool, script: Path | None = None, blender: str | Path | None = None,
        preview: bool = True, say=print) -> None:
    """Blender on ``s`` and a pass per save (module docstring); each pass's
    lines through ``say``."""
    from devkit.models.blender.batch import slot
    from devkit.models.preview import find_blender

    check_mode(headless, script)
    exe = find_blender(blender)
    job = _job(s, Path(script).absolute() if script else None, headless)
    session = Path(__file__).parent / "blender" / "edit_session.py"
    opened = [str(s.work / BLEND)] if (s.work / BLEND).is_file() else []
    done = _saves(s)
    if headless:
        argv = [str(exe), "--background", "--factory-startup", *opened, "--python-exit-code", "1",
                "--python", str(session), "--", str(job)]
        with slot() as held:                # at most 8 Blenders on the machine (Step X.62)
            ran = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, cwd=s.work, pass_fds=held.fds)
        tail = " | ".join([x for x in (ran.stdout + ran.stderr).splitlines() if x.strip()][-4:])
        if ran.returncode != 0:
            raise ValueError(f"Blender failed ({ran.returncode}): {tail}")
        if _saves(s) == done:
            raise ValueError(f"Blender saved nothing (the --script or the save's export failed): {tail}")
        run_pass(s, blender=exe, preview=preview, say=say)
        return
    proc = subprocess.Popen([str(exe), *opened, "--python", str(session), "--", str(job)], cwd=s.work)
    say(f"Blender is open on {s.work / BLEND}: each save (Ctrl+S) is read back here; close Blender to end")
    while True:
        alive = proc.poll() is None
        now = _saves(s)
        if now > done:
            done = now
            run_pass(s, blender=exe, preview=preview, say=say)
        elif not alive:
            break
        else:
            time.sleep(POLL)


def _unplayed(s: Session, animations: list[str]) -> list[str]:
    """The animations that are the body's own clips and that no recipe
    column plays: a build stores them as ``v/<name>``, which only a
    column plays, so they would play nowhere (module docstring)."""
    from azurkit.tools.characters.characters import read_body

    own = {c.casefold() for c in read_body(s.characters, s.body).clips}
    columns = s.recipe.get("columns") if isinstance(s.recipe.get("columns"), dict) else {}
    played = {c for c in columns.values() if isinstance(c, str)}
    return [a for a in animations if a.casefold() in own and a not in played]


def _recipe_with(s: Session, sha: str, animations: list[str]) -> dict:
    recipe = json.loads(json.dumps(s.recipe))
    mesh = recipe.get("mesh") if isinstance(recipe.get("mesh"), dict) else {}
    recipe["mesh"] = {**mesh, "gltf": {"file": SAVED, "sha256": sha, "import": s.mode}}
    clips = recipe.get("clips") if isinstance(recipe.get("clips"), dict) else {}
    for name in animations:
        given = clips.get(name) if isinstance(clips.get(name), dict) else {}
        clips[name] = {**given, "generator": "gltf", "file": SAVED, "sha256": sha, "animation": name}
    if clips:
        recipe["clips"] = clips
    return recipe


def _worn(s: Session):
    """The session's config.xbr as W1 leaves it, the player wearing the
    body (his ``critters_engine`` ``body`` cell): its document and that
    section, where W36 reads who wears the body and casts its shadow."""
    from azurkit.tools.characters._player_character import PLAYER
    from azurkit.tools.characters.ports import XbrDocument, point_keyed_string

    doc = XbrDocument.from_bytes(s.config)
    engine = doc.keyed_section("critters_engine")
    if s.species != PLAYER:
        point_keyed_string(engine, PLAYER, "body", s.species, "body")
    return doc, engine


def run_pass(s: Session, *, blender=None, preview: bool = True, say=print) -> dict:
    """One pass on ``DIR/edit.glb`` (module docstring): its log row."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import clip_import, mesh_edit, model_inspect
    from azurkit.tools.characters._player_character import _shadow_ahead, write_lods, write_shadow_lod
    from devkit.models import preview as model_preview

    s.passes += 1
    k = s.passes
    glb = s.work / SAVED
    row: dict = {"pass": k, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        if (s.work / RECIPE).is_file():     # with any edit made to it since the last pass
            s.recipe = json.loads((s.work / RECIPE).read_text(encoding="utf-8"))[s.name]
        doc, _, sha = mesh_edit._load(glb)
        row["sha256"] = sha
        animations = [str(a.get("name", "")) for a in doc.get("animations", [])]
        unplayed = _unplayed(s, animations)
        animations = [a for a in animations if a not in unplayed]
        if unplayed:
            row["unplayed"] = unplayed
        recipe = _recipe_with(s, sha, animations)
        variant = variants.load_variants(json.dumps({s.name: recipe}), str(s.work / RECIPE))[s.name]
        with _building(s.iso):
            plan = mesh_edit.plan(s.characters, s.body, variant.mesh, s.work)
            got_mesh = plan.imported
            if got_mesh is not None:
                row["imported"] = {k: getattr(got_mesh, k) for k in ("kept", "changed", "removed", "added")}
            edited = bytearray(s.characters)
            mesh_edit.write(edited, plan, s.characters)
            written, index = bytes(edited), s.index
            if animations:
                got = clip_import.read_clips(written, s.body, glb, animations)
                written, index = clip_import.write_clips(written, index, s.body, got)
                row["clips"] = {c.name: {"seconds": round(c.clip.length, 3), "keys": c.keys_after,
                                         "root_travel": round(c.root_travel, 4)} for c in got}
            out = s.work / f"pass-{k}"
            out.mkdir()
            (out / "characters.xbr").write_bytes(written)
            (out / "index.xbr").write_bytes(index)
            config, engine = _worn(s)
            if preview:     # W36's cut in a worker while Blender draws (Step 2.179's cut ahead)
                _shadow_ahead(written, engine, s.body, s.body, variant.shadow)
                shown = model_preview.preview(written, s.body, s.work / "previews" / str(k), blender=blender,
                                              protect=(s.iso,), vanilla=False)
                row["previews"] = sorted(shown["views"].values())
            built = {"characters.xbr": bytearray(written)}
            write_lods(built, engine, s.body, variant.lods, s.characters)   # W39 and W36, as the build gives the
            write_shadow_lod(built, engine, s.body, variant.shadow)         # body its LODs
            report = model_inspect.inspect(bytes(built["characters.xbr"]), s.body, config_xbr=bytes(config.raw),
                                           bake=s.bake, ram=s.ram)
        lod = report.get("lods", [{}])[0]
        own = report.get("own_runs", {})
        row |= {"vertices": lod.get("vertices"), "triangles": lod.get("triangles"), "groups": lod.get("groups"),
                "lods": [{k: n[k] for k in ("lod", "triangles", "push_bytes", "bmsh_bytes", "run_bytes")}
                         | {"share": n["share"]["triangles"], "drawn": n.get("drawn")} for n in report.get("lods", [])],
                "bones": report.get("bones"),
                "own_runs_mib": round((own.get("bytes", 0) + s.bake) / model_inspect.MiB, 3),
                "bake_mib": round(s.bake / model_inspect.MiB, 3),
                "budgets": [f"{b['level']}: {b['what']}" for b in report["budgets"] if b["over"]],
                "problems": report["problems"]}
        errors = report["problems"] or [b for b in report["budgets"] if b["level"] == "error"]
        if errors:
            raise ValueError(f"model inspect: {len(report['problems'])} problems, "
                             f"{sum(b['level'] == 'error' for b in report['budgets'])} budgets past their error")
        s.recipe = recipe
        (s.work / RECIPE).write_text(json.dumps({s.name: recipe}, indent=1), encoding="utf-8")
        row["ok"] = True
        moved = row.get("imported", {})
        lines = [f"pass {k}: {row['vertices']} vertices, {row['triangles']} triangles, {row['groups']} groups, "
                 f"{row['bones']} bones, own runs {row['own_runs_mib']} MiB as built ({row['bake_mib']} of it "
                 "what the build bakes)"
                 + (f"; vertices {moved['kept']} kept, {moved['changed']} changed, {moved['added']} added, "
                    f"{moved['removed']} removed" if moved else "")
                 + (f", clips {', '.join(row['clips'])}" if animations else "") + f"; recipe {RECIPE} written",
                 *(f"  {model_inspect.lod_line(report, n)}" for n in report.get("lods", [])),
                 *(f"  {b}" for b in row["budgets"]),
                 *([f"  left out: {', '.join(unplayed)}: an edit of the body's own clip plays nowhere in a build "
                    "(a recipe's clip plays only in its columns): rename the action, or play it in a column"]
                   if unplayed else [])]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        row |= {"ok": False, "error": str(exc)}
        lines = [f"pass {k} refused: {exc}"]
    s.last_ok = row["ok"]
    with (s.work / LOG).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    for line in lines:
        say(line)
    return row


def build(s: Session, out: Path, say=print) -> str:
    """``out`` (a new image) built from the same release's vanilla image and
    the last passing pass's recipe (module docstring); the build's grade
    line."""
    from azurkit import sdk
    from devkit.models import dress

    if not s.last_ok:
        raise ValueError("--build: the last pass didn't pass (log.jsonl names why); no image is built")
    out = Path(out).absolute()
    check_build_out(out, s.iso)
    built = sdk.build({"iso": str(s.iso), "packs": dress.packs(s.ram),
                       "character": {"species": s.name, "variant_file": str(s.work / RECIPE), "ram": s.ram}}, str(out))
    graded = [n for n in built["notes"] if n.startswith("Player model status")] or ["(no grade line)"]
    say(f"built {out}: {graded[-1]}")
    return graded[-1]


def check_build_out(out: Path, iso: Path) -> None:
    """``--build``'s output may be written (D36), checked before Blender opens."""
    out = image.output(out, iso, file=True, flag="--build")
    if out.exists():
        raise ValueError(f"--build {out} exists already; give a new file")


__all__ = ["AGENT_ENV", "Session", "build", "check_build_out", "check_mode", "prepare", "run", "run_pass"]
