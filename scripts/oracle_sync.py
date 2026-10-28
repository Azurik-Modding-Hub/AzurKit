"""Copy Modkit's oracle bundle for the given families into ``tests/oracle/``.

    uv run --locked python scripts/oracle_sync.py --modkit PATH --ref REF --tag NAME --family core --family packs

The script clones Modkit at REF into a scratch folder. It uses ``git clone
--shared``, so Modkit's checkout and refs are left as they are. It then runs
Modkit's own ``scripts/export_oracle.py`` there, in Modkit's locked
environment, and replaces each family's folder in ``tests/oracle/`` with the
bundle's. ``tests/oracle/ORACLE.toml`` records each family's tag (the Modkit
tag the bundle is cut at), its commit and the sha256 of every file;
``tests/test_oracle.py`` checks every file against it.

When a family was synced before, the script prints Modkit's commits since that
sync that touch the family's paths. That list is the port's to-do. AzurKit never
imports Modkit: the bundle holds sha256s, names and recipes (never game bytes).
The facts' build spans (``patch_sites.<va>.new.<case>``, a build's bytes over
a site, vanilla code included where the pack leaves it) are installed as their
sha256 and size (:func:`digest_spans`); ORACLE.toml's ``exported`` table keeps
each such file's sha256 as exported, which Modkit's ``oracle.json`` lists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORACLE = ROOT / "tests" / "oracle"
FAMILIES = ("core", "packs", "rando", "models")
FACTS = ("tests/facts/xbe.json", "tests/facts/xbe.europe.json")   # their build spans are installed as digests
PATHS = {   # where each family's code and records live in Modkit (its tag bump's commit list)
    "core": ("azurik_mod/iso", "azurik_mod/assets/vanilla.py", "azurik_mod/assets/filelist.py",
             "azurik_mod/assets/vanilla_manifest.json", "azurik_mod/assets/europe_manifest.json",
             "azurik_mod/assets/region_europe.json"),
    "packs": ("azurik_mod/patches", "azurik_mod/patching", "azurik_mod/xbe_tools", "azurik_mod/xbr",
              "azurik_mod/config", "shims", "tests/facts", "tests/goldens/packs.json",
              "tests/goldens/europe/packs.json", "tests/goldens/shims.json", "tests/goldens/xbr_editor.json",
              "tests/goldens/pipelines.json", "tests/goldens/gui.json"),
    "rando": ("azurik_mod/randomizer", "tests/goldens/rando_plans.json", "tests/goldens/rando_iso.json"),
    "models": ("azurik_mod/patches/player_model", "azurik_mod/patches/_player_character.py", "azurik_mod/assets"),
}


def read_index(path: Path = ORACLE / "ORACLE.toml") -> dict[str, dict]:
    """``{family: {"tag", "commit", "files": {path: sha256}[, "exported": {path: sha256}]}}``; empty when there
    is no index."""
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_index(index: dict[str, dict], path: Path = ORACLE / "ORACLE.toml") -> None:
    lines = ["# Written by scripts/oracle_sync.py, never by hand: tests/test_oracle.py checks every file of",
             "# tests/oracle/<family>/ against its sha256 here; <family>.exported holds a facts file's sha256",
             "# as Modkit exported it, before its build spans became sha256 and size."]
    for family in sorted(index):
        entry = index[family]
        lines += ["", f"[{family}]", f"tag = {json.dumps(entry['tag'])}", f"commit = {json.dumps(entry['commit'])}",
                  "", f"[{family}.files]"]
        lines += [f"{json.dumps(rel)} = {json.dumps(sha)}" for rel, sha in sorted(entry["files"].items())]
        if exported := entry.get("exported"):
            lines += ["", f"[{family}.exported]"]
            lines += [f"{json.dumps(rel)} = {json.dumps(sha)}" for rel, sha in sorted(exported.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def tree_hashes(folder: Path) -> dict[str, str]:
    """``{posix path: sha256}`` of every file under ``folder``."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def digest_spans(path: Path) -> str:
    """Replace each build span of the facts file ``path`` (a hex string at
    ``patch_sites.<va>.new.<case>``) with ``{"sha256", "size"}`` of its bytes;
    returns the file's sha256 as it was."""
    raw = path.read_bytes()
    facts = json.loads(raw)
    for site in facts["patch_sites"].values():
        for case, hexed in site.get("new", {}).items():
            span = bytes.fromhex(hexed)
            site["new"][case] = {"sha256": hashlib.sha256(span).hexdigest(), "size": len(span)}
    path.write_text(json.dumps(facts, indent=1) + "\n", encoding="utf-8")
    return hashlib.sha256(raw).hexdigest()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def sync(modkit: Path, ref: str, tag: str, families: tuple[str, ...]) -> list[str]:
    """Export ``families`` from Modkit at ``ref`` and install them; returns the lines to print."""
    commit = _git(modkit, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    index, out = read_index(), []
    with tempfile.TemporaryDirectory(prefix="azurkit-oracle-") as scratch:
        clone, bundle = Path(scratch, "modkit"), Path(scratch, "bundle")
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(modkit), str(clone)], check=True)
        _git(clone, "checkout", "--quiet", "--detach", commit)
        env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
        argv = ["uv", "run", "--locked", "--directory", str(clone), "python", "scripts/export_oracle.py", str(bundle),
                "--tag", tag, *(a for f in families for a in ("--family", f))]
        subprocess.run(argv, check=True, env=env)
        for family in families:
            meta = json.loads((bundle / family / "oracle.json").read_text(encoding="utf-8"))
            if meta["commit"] != commit or meta["dirty"]:
                raise SystemExit(f"{family}: the bundle is from {meta['commit']} (dirty: {meta['dirty']}), not {commit}")
            if old := index.get(family, {}).get("commit"):
                todo = _git(modkit, "log", "--oneline", f"{old}..{commit}", "--", *PATHS[family]).splitlines()
                out += [f"{family}: {len(todo)} Modkit commits since {old[:12]} touch its paths (the port's to-do):",
                        *(f"  {line}" for line in todo)]
            shutil.rmtree(ORACLE / family, ignore_errors=True)
            shutil.copytree(bundle / family, ORACLE / family)
            exported = {rel: digest_spans(ORACLE / family / rel) for rel in FACTS if (ORACLE / family / rel).exists()}
            index[family] = {"tag": tag, "commit": commit, "files": tree_hashes(ORACLE / family)}
            index[family] |= {"exported": exported} if exported else {}
            out.append(f"{family}: {len(index[family]['files'])} files at {tag} ({commit[:12]})")
    write_index(index)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--modkit", type=Path, default=os.environ.get("AZURKIT_MODKIT"),
                    help="Modkit's checkout (default $AZURKIT_MODKIT)")
    ap.add_argument("--ref", required=True, help="the Modkit commit, branch or tag to export at")
    ap.add_argument("--tag", required=True, help="the Modkit tag the bundle is cut at (recorded)")
    ap.add_argument("--family", action="append", choices=FAMILIES, required=True)
    args = ap.parse_args(argv)
    if args.modkit is None:
        ap.error("--modkit or $AZURKIT_MODKIT names Modkit's checkout")
    for line in sync(args.modkit, args.ref, args.tag, tuple(dict.fromkeys(args.family))):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
