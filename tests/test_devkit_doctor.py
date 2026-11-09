"""``python -m devkit doctor`` (``devkit/doctor``, Step 4.24a; Modkit's
``azurik-mod doctor`` and its test_setup doctor tests, merged and lean): one
line a check of AzurKit's own tools, a failure of each required one named,
an optional one ok either way, and its places outside the checkout listed
once each. On a fake checkout: no game bytes, never the developer's git
config, Ghidra or disk."""

from __future__ import annotations

import shutil
import subprocess
import types

from devkit import __main__ as devkit_main
from devkit import doctor
from devkit.re import ghidra_serve
from devkit.re.ghidra_client import GhidraClient, GhidraClientError
from devkit.reach import l3_fast
from tests._xiso import fill, image


def test_doctor_names_each_broken_required_check_warns_otherwise_and_lists_each_place_it_writes_once(
        tmp_path, monkeypatch, capsys):
    """A checkout with no uv.lock, a modded USA image and no Europe one, no web tools, a stale RE tool's stamp
    and an extension installed twice fails those checks by name and exits 1; the optional tools, a busy Ghidra
    and a closed project are ok; the disk under 50 GiB, a push with no leak guard and a cloud-synced checkout
    are warnings. ``--uninstall-hints`` names each folder once, the user data and cache folders among them, and
    ``python -m devkit doctor`` runs it as a command of its own."""
    root = tmp_path / "Library" / "CloudStorage" / "repo"
    (root / "devkit" / "re").mkdir(parents=True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "global.gitconfig"))   # never the developer's
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("UV_OFFLINE", "1")
    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=60)
    (root / "pyproject.toml").write_text('[project]\nname = "fake"\nversion = "0"\n', encoding="utf-8")  # no uv.lock
    (root / "devkit" / "re" / "tools.toml").write_text(
        'schema = 1\n[tools.jdk]\nversion = "21.0.12.1+1"\nkind = "archive"\n'
        'assets.any = { url = "https://example.invalid/jdk.zip", sha256 = "ab12" }\n', encoding="utf-8")
    (root / ".tools" / "jdk").mkdir(parents=True)
    (root / ".tools" / "jdk" / ".ok").write_text("21.0.11+9 ab12", encoding="utf-8")   # an older install's stamp
    (root / ".tools" / "ghidra" / "Ghidra" / "Extensions" / "Ghydra").mkdir(parents=True)
    (root / ".tools" / "ghidra-home" / "ghidra" / "ghidra_12.1.2_PUBLIC" / "Extensions" / "Ghydra").mkdir(parents=True)
    modded = tmp_path / "modded.iso"
    modded.write_bytes(image({"default.xbe": fill("x", 20)}))
    monkeypatch.setenv("AZURKIT_ISO", str(modded))
    monkeypatch.setenv("AZURKIT_ISO_EUROPE", str(tmp_path / "none.iso"))

    def busy(client):   # never the real port: a Ghidra mid-analysis is no failure
        raise GhidraClientError(message=f"Request to {client.base_url} timed out", code="REQUEST_TIMEOUT")
    monkeypatch.setattr(GhidraClient, "program_info", busy)
    project = tmp_path / "ghidra" / "P.gpr"   # never the owner's: the one ghidra-serve remembers
    monkeypatch.setattr(ghidra_serve, "remembered_project", lambda: project)
    monkeypatch.setattr(l3_fast, "probe", lambda: {"lib": "stock", "sha12": "0" * 12, "switches": {}})
    monkeypatch.setattr(shutil, "disk_usage", lambda path: types.SimpleNamespace(free=50 * 2**30 - 2**20))

    assert doctor.run(root) == 1
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(": ")[0] for line in lines] == [
        "ok    Python 3.14", "ok    uv", "FAIL  uv.lock in sync", "FAIL  USA image", "FAIL  Europe image", "ok    zig",
        "ok    mcp", "ok    libunicorn", "FAIL  web tools", "ok    Blender", "ok    ffmpeg", "ok    xemu",
        "FAIL  RE tools", "ok    Ghidra endpoint", "ok    Ghidra project", "warn  disk", "warn  leak-guard hook",
        "warn  sync root", "doctor"]
    said = dict(line.split(": ", 1) for line in lines)
    assert said["FAIL  uv.lock in sync"].endswith("(`uv lock` updates it)")
    assert said["FAIL  USA image"].startswith(f"{modded} is not the vanilla USA image: ")
    assert said["FAIL  Europe image"] == f"AZURKIT_ISO_EUROPE names no file ({tmp_path / 'none.iso'})"
    assert said["ok    zig"] == "zig 0.16.0; the pentium3 probe compiles to the pinned code"
    assert said["FAIL  RE tools"].startswith("jdk: .ok stamp missing or not the ") and said["FAIL  RE tools"].endswith(
        "; ghidra-home/ghidra/ghidra_12.1.2_PUBLIC/Extensions/Ghydra duplicates .tools/ghidra's Ghydra: delete it")
    assert said["ok    Ghidra project"] == f"closed: {project}"
    assert said["warn  disk"].endswith("under 50 GiB: a build, a test run or an xemu sitting may run out of room")
    assert said["warn  leak-guard hook"].startswith("not hooked: ") and "missing (`uv run bootstrap.py` writes it)" in (
        said["warn  leak-guard hook"])
    assert lines[-1] == "doctor: 5 check(s) failed"

    from platformdirs import user_cache_dir, user_data_dir
    folders = [line.split("  ", 1)[0] for line in doctor.uninstall_hints()]
    assert len(folders) == len(set(folders)) and {user_data_dir("AzurKit", appauthor=False),
                                                   user_cache_dir("AzurKit", appauthor=False)} <= set(folders)
    assert devkit_main.main(["doctor", "--uninstall-hints"]) == 0
    assert capsys.readouterr().out.startswith("Deleting the checkout removes .venv and .tools/")
