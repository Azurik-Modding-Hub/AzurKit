"""The landing tools: ``scripts/fullsuite.py``'s changed-area plan and
``scripts/land.py``'s gate: a passing receipt, and no vanilla run added by
any commit it lands."""

from __future__ import annotations

import json
import subprocess

from azurkit.core import facts, gate
from scripts import fullsuite, land

SMOKE = sorted(fullsuite.SMOKE)


def test_the_changed_area_plan_picks_importers_and_falls_back_to_the_whole_suite():
    """A changed module selects every test file that reaches it through
    imports; src/ adds the wheel's test; docs and tests/oracle/ select only
    the smoke files (the lint files and the oracle's USA and Europe test);
    the suite's configuration, what every session loads and an unknown path
    make it whole."""
    deps = {"azurkit": set(), "azurkit.core": {"azurkit"}, "azurkit.core.iso": {"azurkit", "azurkit.core"},
            "azurkit.core.gate": {"azurkit", "azurkit.core"},
            "azurkit.sdk": {"azurkit", "azurkit.core", "azurkit.core.iso"},
            "tests.conftest": {"azurkit", "azurkit.core", "azurkit.core.gate"},
            "tests.test_sdk": {"azurkit", "azurkit.sdk"}, "tests.test_oracle": {"azurkit.core.iso"},
            "tests.test_wheel": {"azurkit"}, "tests.test_other": {"json"}}
    assert "tests/test_oracle.py" in SMOKE
    assert fullsuite.plan(["src/azurkit/core/iso.py"], deps) == sorted(
        {*SMOKE, "tests/test_sdk.py", "tests/test_wheel.py"})
    assert fullsuite.plan(["tests/test_other.py", "README.md", "tests/provenance/jtcpp_lines.txt"], deps) == sorted(
        {*SMOKE, "tests/test_other.py"})
    assert fullsuite.plan(["tests/oracle/core/oracle.json", "bootstrap.py"], deps) == SMOKE
    for whole in ("pyproject.toml", "uv.lock", "tests/conftest.py", "src/azurkit/core/gate.py", "web/index.html"):
        assert fullsuite.plan([whole], deps) is None, whole


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _repo(tmp_path, monkeypatch):
    """A repository whose main has one commit, a lane worktree on ``p2/x``
    and an empty receipts folder: ``(repo, lane, receipts, main's commit)``."""
    repo, lane, receipts = tmp_path / "repo", tmp_path / "lanes" / "x", tmp_path / "receipts"
    monkeypatch.setenv("AZURKIT_RECEIPTS", str(receipts))
    receipts.mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _git(repo, "commit", "-q", "--allow-empty", "-m", "a")
    _git(repo, "worktree", "add", "-q", "-b", "p2/x", str(lane), "main")
    return repo, lane, receipts, _git(repo, "rev-parse", "HEAD")


def _receipt(receipts, head, **fields):
    m = {"key": f"{head[:12]}-0", "head": head, "clean": True, "state": "done", "exit_code": 0, "mode": "full",
         "base": None, "finished_at": "2026-10-28T00:00:00", "vanilla_run": 2, "europe_run": 1} | fields
    (receipts / f"suite-{m['key']}.meta").write_text(json.dumps(m), encoding="utf-8")


def test_land_fast_forwards_main_only_with_a_passing_receipt_and_removes_the_lane(tmp_path, monkeypatch,
                                                                                  usa_iso, europe_iso):
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    _git(lane, "commit", "-q", "--allow-empty", "-m", "b")
    top = _git(lane, "rev-parse", "HEAD")
    _git(repo, "branch", "p2/y", base)
    for refused in ({"exit_code": 1}, {"vanilla_run": 0}, {"europe_run": None}):   # D26: both tiers ran
        _receipt(receipts, top, **refused)
        assert land.land(repo, "p2/x")[0] == 1, refused
    _receipt(receipts, top[:11] + "f", clean=False)
    assert land.land(repo, "p2/x")[0] == 1
    _receipt(receipts, top, mode="changed", base=base)
    assert land.land(repo, "p2/x") == (0, f"land: moved main {base[:12]} -> {top[:12]} (p2/x; receipt "
                                          f"{top[:12]}-0, changed)")
    assert _git(repo, "rev-parse", "main") == top and not lane.exists()
    assert _git(repo, "branch", "--list", "p2/x") == ""
    _git(repo, "switch", "-q", "p2/y")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "c")
    _receipt(receipts, _git(repo, "rev-parse", "HEAD"))
    code, why = land.land(repo, "p2/y")
    assert code == 1 and "doesn't fast-forward from main" in why


def test_land_refuses_a_vanilla_run_a_later_commit_of_the_stack_removes(tmp_path, monkeypatch, usa_iso,
                                                                         europe_iso):
    """A stack whose first commit adds a literal holding 13 bytes of the USA
    default.xbe (read from the image here; 4.1c's fps_unlock held them) and
    whose second removes it again has a clean head and a passing receipt,
    and land still refuses it: it names the first commit, the file, the
    line and the lengths, never the bytes, and moves nothing."""
    files = land.vanilla_files()
    run = files["USA default.xbe"][facts.of(gate.USA).offset(0x059B37, 30):][17:30]
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    (lane / "src").mkdir()
    (lane / "src" / "a.py").write_text(f'N = 1\nX = bytes.fromhex("{run.hex()}")\n', encoding="utf-8")
    _git(lane, "add", "src/a.py")
    _git(lane, "commit", "-q", "-m", "a vanilla run")
    planted = _git(lane, "rev-parse", "HEAD")
    (lane / "src" / "a.py").write_text("N = 1\n", encoding="utf-8")
    _git(lane, "commit", "-q", "-am", "gone again")
    top = _git(lane, "rev-parse", "HEAD")
    _receipt(receipts, top, mode="changed", base=base)
    code, why = land.land(repo, "p2/x")
    assert code == 1 and why.splitlines()[1:] == [
        f"src/a.py:2 in {planted[:12]}: a 13 B literal holds 13 B in a row of the {name}"
        for name, data in files.items() if run in data]
    assert not any(form in why.lower() for form in (run.hex(), run.hex(" "), repr(run).lower()))
    assert (_git(repo, "rev-parse", "main"), _git(lane, "rev-parse", "HEAD")) == (base, top)
