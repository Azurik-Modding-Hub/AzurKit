"""The reach engine's outcome cache (Step R2.16a; the R2.16 design §2e): one private file per job in the AzurKit user
cache, written atomically (AZ-640: a killed run leaves no half file).

A job's key is the sha256[:12] of what its outcomes depend on and nothing else: the L3 core (:func:`core_sha12`:
the simulator's own code and its overlay, the RAM recipes, the pad's geometry, the observation reader, the witness
format (``l3_search``'s segments and ``CAST_WAIT``), the flap law's constants (the randomizer's ``physics.py``), the
launch controllers and this engine's runner, and Unicorn's version; for an aimed job (one with a ``target``) the
targeted pass's code too (:data:`AIM_FILES`, Step R2.16d: so an aim-only change re-runs no fan job, 89 % of w1's
ticks); not L3's ``engine_sha12``, which hashes the randomizer's data too, ``devkit/sim/l3.py``'s ENGINE_FILES), the
snapshot's metadata hash, the launch set's version
(``reach_engine.R0``), the volumes and pickups the plan judges touches against (its targets file's sha12) and the
job itself (its start feet, heading, cells and macros).  The derived data is no part of it: a derive change keeps
every outcome and re-maps it to nodes and zones (each outcome keeps where it settled, privately), and only an L3
core or launch change runs them again.  The folder is mode 700 and its files 0600: outcomes hold positions and the
witness strings; they are never committed or printed.
"""

from __future__ import annotations

import functools
import gzip
import hashlib
import json
import os
from pathlib import Path

from devkit.reach import engine as reach_engine

CORE_FILES = ("devkit/sim/l3.py", "devkit/sim/l2.py", "devkit/sim/overlay.py",
              "src/azurkit/tools/randomizer/live/recipes.py", "devkit/sim/inputs.py", "devkit/sim/obs.py",
              "src/azurkit/tools/randomizer/live/pages.py", "devkit/sim/faces.py", "devkit/sim/tricks_detect.py",
              "devkit/sim/l3_search.py", "src/azurkit/tools/randomizer/physics.py", "devkit/rando/physics.py",
              "devkit/reach/engine/macros.py", "devkit/reach/engine/runner.py")   # Modkit's, at their AzurKit homes
                                                                                  # (physics: both halves)
AIM_FILES = ("devkit/reach/engine/aim.py", "devkit/reach/engine/hold.py")   # the targeted pass (its hits held): an
                                                                             # aimed job's core only
ZONE_FILES = ("devkit/rando/draft/route.py", "devkit/reach/engine/nodes.py")   # the code that names a zone
                                                                                # (``nodes.Zones``)


def folder(level: str, root: str | Path | None = None) -> Path:
    """``root`` (default the user cache dir's ``AzurKit/reach-engine``) ``/<level>``, made mode 700; a folder
    anyone else may enter is refused (outcomes hold positions)."""
    from platformdirs import user_cache_dir
    base = Path(root) if root is not None else Path(user_cache_dir("AzurKit")) / "reach-engine"
    p = base / level
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    for q in (base, p):
        q.chmod(0o700)
    return p


_C_PUNCT = sorted(("...", "<<=", ">>=", "->", "++", "--", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||", "*=", "/=",
                   "%=", "+=", "-=", "&=", "^=", "|=", "##"), key=len, reverse=True)


def c_tokens(text: str) -> list[str]:
    """C source as its tokens (maximal munch: ``a--b`` is ``a -- b``, ``a - -b`` is ``a - - b``): comments dropped,
    string and character literals kept whole (a ``//`` inside one is no comment), each preprocessor line ended by a
    ``\\n`` token (a line continuation joins it to the next)."""
    out, i, n, directive, bol = [], 0, len(text), False, True
    while i < n:
        c = text[i]
        if c == "\\" and text.startswith("\n", i + 1):
            i += 2
            continue
        if c == "\n":
            if directive:
                out.append("\n")
            directive, bol, i = False, True, i + 1
            continue
        if c in " \t\r\f\v":
            i += 1
            continue
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "#" and bol:
            directive = True
        bol = False
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
            continue
        if c.isalnum() or c == "_" or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_." or (text[j] in "+-" and text[j - 1] in "eEpP"
                                                                         and (c.isdigit() or c == "."))):
                j += 1
            out.append(text[i:j])
            i = j
            continue
        p = next((p for p in _C_PUNCT if text.startswith(p, i)), c)
        out.append(p)
        i += len(p)
    return out


def code_bytes(path: Path) -> bytes:
    """What a key hashes of a source file (Step R2.19f+, SF0: an edit that changes no code moves no key): a ``.py``
    file's AST without docstrings (``ast.dump``), a ``.c`` or ``.h`` file's tokens (:func:`c_tokens`, one space
    apart), any other file's bytes."""
    import ast
    if path.suffix == ".py":
        tree = ast.parse(path.read_bytes(), str(path))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body
                    and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:]
        return ast.dump(tree, include_attributes=False).encode()
    if path.suffix in (".c", ".h"):
        return " ".join(c_tokens(path.read_text(encoding="utf-8"))).encode()
    return path.read_bytes()


def code_sha12(*paths: Path) -> str:
    """sha256[:12] of the :func:`code_bytes` of ``paths``, in order."""
    h = hashlib.sha256()
    for p in paths:
        h.update(code_bytes(Path(p)))
    return h.hexdigest()[:12]


def core_sha12(root: str | Path | None = None, files=CORE_FILES) -> str:
    """sha256[:12] of the L3 core's files (:data:`CORE_FILES` under ``root``, by default the checkout's root: each
    path and its code, :func:`code_bytes`, in order) and Unicorn's version."""
    import unicorn
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    h = hashlib.sha256(f"unicorn {unicorn.__version__}\n".encode())
    for rel in files:
        h.update(f"{rel}\n".encode() + code_bytes(root / rel))
    return h.hexdigest()[:12]


@functools.cache
def core(files=CORE_FILES) -> str:
    """:func:`core_sha12` of this checkout's ``files``, once per process."""
    return core_sha12(files=files)


def job_key(job: dict, meta_sha12: str, core12: str | None = None, touch: str | None = None,
            zones12: str | None = None) -> str:
    """A job's key: sha256[:12] of the core (``core12``, by default :data:`CORE_FILES`' sha12, an aimed job's with
    :data:`AIM_FILES`), the snapshot's metadata hash, the launch set's version, the plan's targets (``touch``, their
    file's sha12) and the job's start (feet lists, heading, cells, macros, an aim's target, its cells, stop,
    certificate and edge: its confidence decides ``aim.MORE``'s passes, its flap schedule, a refinement's twin's
    answers and whether it asks for every pass, ``more``), and for a job that stops (``aim.hit``) the code that names its zones (``zones12``, by default
    :data:`ZONE_FILES`' sha12); its ``id`` and bookkeeping fields aren't part."""
    core12 = core12 or core(CORE_FILES + AIM_FILES if job.get("target") is not None else CORE_FILES)
    doc = {"core": core12, "meta": meta_sha12, "r0": reach_engine.R0, "touch": touch,
           **{k: job[k] for k in ("takeoff_feet", "starts", "heading", "cells", "macros", "target", "aim", "stop",
                                  "target_cells", "cert", "edge", "env", "twin", "more") if k in job}}
    if job.get("stop"):
        doc["zones"] = zones12 or core(ZONE_FILES)
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12]


def path(base: Path, key: str) -> Path:
    return base / key[:2] / f"{key}.json.gz"


def put(base: Path, key: str, doc: dict) -> Path:
    """Write ``doc`` as the job ``key``'s file, gzipped (a job's record is about 37 KB of JSON: its witness
    strings hold the camera's f32 pair each tick), atomically (:func:`write`)."""
    return write(path(base, key), doc, zipped=True)


def sha12(doc) -> str:
    """sha256[:12] of ``doc`` as :func:`write` writes it."""
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def write(p: Path, doc, zipped: bool = False) -> Path:
    """``doc`` as JSON at ``p`` (``zipped``: gzipped), atomically (:func:`write_bytes`)."""
    text = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    return write_bytes(p, gzip.compress(text, 6, mtime=0) if zipped else text)


def write_bytes(p: Path, data: bytes) -> Path:
    """``data`` at ``p``, atomically (a temporary file, mode 0600, then a rename), its folder mode 700."""
    p.parent.mkdir(mode=0o700, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, p)
    return p


def get(base: Path, key: str) -> dict | None:
    """The job ``key``'s file, None when it isn't there."""
    try:
        return json.loads(gzip.decompress(path(base, key).read_bytes()))
    except FileNotFoundError:
        return None
