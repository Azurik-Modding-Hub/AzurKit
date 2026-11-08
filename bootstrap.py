"""First setup: ``uv sync --locked``, the leak guard's ``pre-push`` hook,
and Pyodide, Chromium, WebKit and Firefox for the site and the ``web`` tests;
with ``--with re``, devkit's Ghidra side too.

    uv run bootstrap.py [--no-hooks] [--no-web] [--with re [--allow-scripts]]

The hook (in the repository's common git dir, so every worktree shares it)
runs ``tests/_leak_guard.py --pre-push`` over every file the pushed commits
add or change, and refuses the push on a hit (D961). Pyodide's core (pinned
by sha256) and Playwright's headless Chromium, WebKit and Firefox go in the main checkout's
``.tools/`` (``scripts/web_tools.py``), which every lane uses. Run this in
the main checkout, not in a lane. Stdlib only.

``--with re`` installs each tool ``devkit/re/tools.toml`` pins for this host
(Ghidra 12.1.2, its Temurin JDK, the ghidra-xbe loader and the stock
GhydraMCP plugin and bridge; dev only, about 1.2 GB) into this checkout's
``.tools/``, each download checked against its sha256 before it is
unpacked, and prints, never runs, the ``claude mcp add`` line for the
bridge. A re-run fetches only what changed; delete the folders to uninstall
(Modkit's ``--with re``, ported in Step 4.11d2).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANAGED = "# --- written by `bootstrap.py --with re`; it rewrites everything below on each run ---"
HOOK = """#!/bin/sh
# leak-guard pre-push hook, written by `uv run bootstrap.py` (AzurKit, D961)
# It runs only tests/_leak_guard.py (stdlib) over every file the pushed
# commits add or change, those no remote-tracking ref of the remote reaches
# (a new remote: the whole history): a push fails while one of them is an ISO
# image or a part of one, an xemu disk, an EEPROM dump, a guest RAM snapshot
# or a private key, even one a later commit deleted, naming each file and the
# commit that added it. Delete this file to remove it.
cd "$(git rev-parse --show-toplevel)" || exit 1
for py in .venv/bin/python .venv/Scripts/python.exe; do
  if [ -x "$py" ]; then exec "$py" -I tests/_leak_guard.py --pre-push "$1"; fi
done
exec uv run --no-sync python -I tests/_leak_guard.py --pre-push "$1"
"""


def install_hook(root: Path = ROOT) -> Path:
    common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    hook = Path(common) / "hooks" / "pre-push"
    if hook.exists() and "leak-guard pre-push hook" not in hook.read_text(encoding="utf-8", errors="replace"):
        raise SystemExit(f"{hook} exists and isn't the leak guard's: merge it by hand")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK, encoding="utf-8")
    os.chmod(hook, 0o755)
    return hook


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-hooks", action="store_true", help="leave the pre-push hook out")
    ap.add_argument("--no-web", action="store_true",
                    help="leave Pyodide and the browsers out (then run pytest -m \"not web\")")
    ap.add_argument("--with", dest="extra", choices=["re"],
                    help="re: Ghidra, its JDK, the ghidra-xbe loader and the stock GhydraMCP plugin and bridge, "
                         "each sha256-checked against devkit/re/tools.toml, into .tools/")
    ap.add_argument("--allow-scripts", action="store_true",
                    help="with --with re: let GhydraMCP's scripts_run execute Java (arbitrary code; turn it off "
                         "again after RE work)")
    args = ap.parse_args(argv)
    if args.allow_scripts and args.extra != "re":
        ap.error("--allow-scripts needs --with re")
    subprocess.run(["uv", "sync", "--locked"], cwd=ROOT, check=True)
    if not args.no_hooks:
        print(f"pre-push hook: {install_hook()}")
    if not args.no_web:
        from scripts import web_tools
        print(f"Pyodide {web_tools.VERSION}: {web_tools.fetch(ROOT)}")
        for engine, (_, label) in web_tools.BROWSERS.items():
            print(f"{label} (the web tests'): {web_tools.fetch_browser(engine, ROOT)}")
    if args.extra == "re":
        print("to add the Ghidra MCP server to Claude Code for this checkout only:\n  "
              + install_re(ROOT, allow_scripts=args.allow_scripts))
    return 0


def install_re(root: Path, allow_scripts: bool) -> str:
    """Install every ``devkit/re/tools.toml`` entry for this host into
    ``root/.tools/<name>/`` (each download sha256-checked before it is
    unpacked; ``.ok`` = ``"<version> <sha256>"``, so a re-run fetches only
    what changed), unzip the Ghidra extensions into the fresh Ghidra, and
    (re)write its ``launch.properties``. Return the ``claude mcp add`` line
    for the bridge, which runs in ``devkit/re/ghidra_bridge.py``'s locked
    script environment (``uv run --locked --script``); it is printed, never
    run. Exit naming the tool when an entry has no asset or hash for this
    host, or a download doesn't match."""
    tools = tomllib.loads((root / "devkit" / "re" / "tools.toml").read_text(encoding="utf-8"))["tools"]
    dot = root / ".tools"
    dot.mkdir(exist_ok=True)
    for name, tool in tools.items():
        _install(dot, name, tool)
    ghidra = dot / "ghidra"
    extensions = ghidra / "Ghidra" / "Extensions"
    for name, tool in tools.items():
        if tool["kind"] == "ghidra-extension":
            (archive,) = (p for p in (dot / name).iterdir() if p.suffix == ".zip")
            with zipfile.ZipFile(archive) as z:
                for top in {Path(n).parts[0] for n in z.namelist()}:
                    shutil.rmtree(extensions / top, ignore_errors=True)
            _unpack(archive, extensions)
    jdk = dot / "jdk"
    if (jdk / "Contents" / "Home").is_dir():  # macOS JDK layout
        jdk = jdk / "Contents" / "Home"
    home = dot / "ghidra-home"
    props = ghidra / "support" / "launch.properties"
    stock = props.read_text(encoding="utf-8").split(MANAGED)[0].rstrip("\n").splitlines()
    ours = [MANAGED, f"JAVA_HOME_OVERRIDE={jdk.as_posix()}",
            f"VMARGS=-Dapplication.settingsdir={home.as_posix()}",
            f"VMARGS=-Dapplication.cachedir={(home / 'cache').as_posix()}",
            f"VMARGS=-Dghidra.user.scripts.dir={home.as_posix()}",  # scripts_run's temp sources, not ~/ghidra_scripts
            "VMARGS=-Dghidra.mcp.bind.host=127.0.0.1",
            "VMARGS=-Dghidra.mcp.cors.origin=http://127.0.0.1:1"]
    if allow_scripts:
        ours.append("VMARGS=-Dghydra.dev.allowScripts=true")
    (home / "ghidra_scripts").mkdir(parents=True, exist_ok=True)  # scripts_run(source) writes there
    props.write_text("\n".join([*(line for line in stock if not line.startswith("JAVA_HOME_OVERRIDE=")),
                                "", *ours, ""]), encoding="utf-8")
    bridge = dot / "ghydra-bridge" / "bridge_mcp_hydra.py"
    # The bridge's own default host is `localhost`, which tries ::1 first (AZ-153's twin).
    return (f"claude mcp add --scope local ghidra -e GHIDRA_HYDRA_HOST=127.0.0.1 -- uv run --locked --script "
            f"{(root / 'devkit' / 're' / 'ghidra_bridge.py').as_posix()} {bridge.as_posix()}")


def host_platform() -> str:
    """``tools.toml``'s platform key: ``macos-arm64``, ``linux-x86_64``, ..."""
    system = {"Darwin": "macos"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    machine = {"aarch64": "arm64", "amd64": "x86_64"}.get(machine, machine)
    return f"{system}-{machine}"


def _install(dot: Path, name: str, tool: dict) -> None:
    """Fetch, verify and unpack one entry into ``dot/name`` unless its
    ``.ok`` stamp already matches; a failed run leaves the old install."""
    host = host_platform()
    asset = tool["assets"].get(host) or tool["assets"].get("any") or {}
    if not asset.get("url") or len(asset.get("sha256", "")) != 64:
        sys.exit(f"bootstrap: tools.toml has no {host} asset with a sha256 for {name}; nothing installed")
    dest, stamp = dot / name, f"{tool['version']} {asset['sha256']}"
    if (dest / ".ok").is_file() and (dest / ".ok").read_text(encoding="utf-8").strip() == stamp:
        return
    print(f"fetching {name} {tool['version']} ...", flush=True)
    with tempfile.TemporaryDirectory(dir=dot, prefix=f".{name}-") as tmp:
        download = Path(tmp, urllib.parse.unquote(Path(urllib.parse.urlparse(asset["url"]).path).name))
        with urllib.request.urlopen(asset["url"], timeout=60) as r, download.open("wb") as f:
            got = _sha256(r, f)
        if got != asset["sha256"]:
            sys.exit(f"bootstrap: {name}: the download's sha256 is {got}, "
                     f"tools.toml pins {asset['sha256']}; nothing installed")
        new = Path(tmp, name)
        if tool["kind"] == "archive":
            _unpack(download, Path(tmp, "x"))
            top = list(Path(tmp, "x").iterdir())
            (top[0] if len(top) == 1 and top[0].is_dir() else Path(tmp, "x")).rename(new)
        else:  # a ghidra-extension zip (unzipped into Ghidra by install_re) or a single file
            new.mkdir()
            download.rename(new / download.name)
        (new / ".ok").write_text(stamp + "\n", encoding="utf-8")
        shutil.rmtree(dest, ignore_errors=True)
        new.rename(dest)


def _sha256(stream, copy_to=None) -> str:
    """The sha256 of everything ``stream`` yields, copied to ``copy_to``."""
    digest = hashlib.sha256()
    while chunk := stream.read(1 << 20):
        digest.update(chunk)
        if copy_to is not None:
            copy_to.write(chunk)
    return digest.hexdigest()


def _unpack(archive: Path, into: Path) -> None:
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive) as t:
            t.extractall(into, filter="data")
        return
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            path = Path(z.extract(member, into))
            if mode := member.external_attr >> 16 & 0o755:  # zipfile drops the exec bits (ghidraRun)
                path.chmod(mode)


if __name__ == "__main__":
    sys.exit(main())
