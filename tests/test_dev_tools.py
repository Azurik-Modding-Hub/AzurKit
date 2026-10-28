"""The landing tools: ``scripts/fullsuite.py``'s changed-area plan and
``scripts/land.py``'s gate."""

from __future__ import annotations

import json
import subprocess

from scripts import fullsuite, land

LINT = sorted(fullsuite.LINT)


def test_the_changed_area_plan_picks_importers_and_falls_back_to_the_whole_suite():
    """A changed module selects every test file that reaches it through
    imports; src/ adds the wheel's test, tests/oracle/ the oracle's; docs
    select only the lint files; the suite's configuration, what every
    session loads and an unknown path make it whole."""
    deps = {"azurkit": set(), "azurkit.core": {"azurkit"}, "azurkit.core.iso": {"azurkit", "azurkit.core"},
            "azurkit.core.gate": {"azurkit", "azurkit.core"},
            "azurkit.sdk": {"azurkit", "azurkit.core", "azurkit.core.iso"},
            "tests.conftest": {"azurkit", "azurkit.core", "azurkit.core.gate"},
            "tests.test_sdk": {"azurkit", "azurkit.sdk"}, "tests.test_oracle": {"azurkit.core.iso"},
            "tests.test_wheel": {"azurkit"}, "tests.test_other": {"json"}}
    assert fullsuite.plan(["src/azurkit/core/iso.py"], deps) == sorted(
        {*LINT, "tests/test_oracle.py", "tests/test_sdk.py", "tests/test_wheel.py"})
    assert fullsuite.plan(["tests/test_other.py", "README.md", "tests/provenance/jtcpp_lines.txt"], deps) == sorted(
        {*LINT, "tests/test_other.py"})
    assert fullsuite.plan(["tests/oracle/core/oracle.json"], deps) == sorted({*LINT, "tests/test_oracle.py"})
    for whole in ("pyproject.toml", "uv.lock", "tests/conftest.py", "src/azurkit/core/gate.py", "web/index.html"):
        assert fullsuite.plan([whole], deps) is None, whole


def test_land_fast_forwards_main_only_with_a_passing_receipt_and_removes_the_lane(tmp_path, monkeypatch):
    def git(cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    repo, lane, receipts = tmp_path / "repo", tmp_path / "lanes" / "x", tmp_path / "receipts"
    monkeypatch.setenv("AZURKIT_RECEIPTS", str(receipts))
    receipts.mkdir()
    git(tmp_path, "init", "-q", "-b", "main", str(repo))
    git(repo, "commit", "-q", "--allow-empty", "-m", "a")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "worktree", "add", "-q", "-b", "p2/x", str(lane), "main")
    git(lane, "commit", "-q", "--allow-empty", "-m", "b")
    top = git(lane, "rev-parse", "HEAD")
    git(repo, "branch", "p2/y", base)

    def receipt(head, **fields):
        m = {"key": f"{head[:12]}-0", "head": head, "clean": True, "state": "done", "exit_code": 0, "mode": "full",
             "base": None, "finished_at": "2026-10-28T00:00:00"} | fields
        (receipts / f"suite-{m['key']}.meta").write_text(json.dumps(m), encoding="utf-8")

    receipt(top, exit_code=1)
    receipt(top[:11] + "f", clean=False)
    assert land.land(repo, "p2/x")[0] == 1
    receipt(top, mode="changed", base=base)
    assert land.land(repo, "p2/x") == (0, f"land: moved main {base[:12]} -> {top[:12]} (p2/x; receipt "
                                          f"{top[:12]}-0, changed)")
    assert git(repo, "rev-parse", "main") == top and not lane.exists()
    assert git(repo, "branch", "--list", "p2/x") == ""
    git(repo, "switch", "-q", "p2/y")
    git(repo, "commit", "-q", "--allow-empty", "-m", "c")
    receipt(git(repo, "rev-parse", "HEAD"))
    code, why = land.land(repo, "p2/y")
    assert code == 1 and "doesn't fast-forward from main" in why
