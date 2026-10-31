"""The agents' files: each role in ``.claude/agents/`` pins its model, the
tracked skills hold no text the Skill tool runs as a shell command, no
tracked text holds a home path, and no doc or skill cites a step's dated
evidence folder.

The roles and skills are tracked here under their ``azurik-*`` names
(D951); the first two guards are Modkit's (``tests/test_retired_names.py``),
ported with the four roles in use (the judge is unused since D457)."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# D281 (amending D241): each role on the model that fits its job; Opus at xhigh where judgment is the job,
# Sonnet for a lookup with cites, Haiku for a handed-over command list.
ROLES = {"azurik-builder": ("opus", "xhigh"), "azurik-reader": ("opus", "xhigh"),
         "azurik-scout": ("sonnet", "medium"), "azurik-mechanic": ("haiku", "medium")}
GHIDRA_WRITERS = (
    "analysis_run comments_set data_create data_delete data_rename data_set_type "
    "datatypes_create_enum datatypes_create_struct datatypes_create_union functions_create "
    "functions_delete functions_rename functions_set_comment functions_set_signature "
    "functions_update_variable memory_write programs_delete programs_save project_open_file "
    "scripts_run structs_add_field structs_create structs_delete structs_update_field").split()

#: The owner's layout in a home folder, by ``~``, ``$HOME`` or an absolute home: the checkouts, lanes and
#: evidence under Documents, the memory and the harness's settings under .claude. The platform's own folders
#: (the user data folder in Library) are no one's home path.
HOME_LAYOUT = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/(?:Users|home)/[^/\s\"'`]+)/(?:Documents|\.claude)\b")
#: A cite of one step's evidence (``$EV/<slug>-<date>/``): private, so a dead link in the public repo.
#: ``$EV/tools/``, what the seats run, is the folder's interface and stays.
DATED_EVIDENCE = re.compile(r"\$EV/[^\s/`'\"]*20\d\d-\d\d-\d\d")


def tracked(*pathspec: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--cached", "-z", *pathspec],
                         capture_output=True, text=True, check=True).stdout
    return [rel for rel in out.split("\0") if rel and (ROOT / rel).is_file()]


def test_every_agent_role_pins_the_model_that_fits_its_job():
    """An unpinned seat runs the session's model, so each role in
    .claude/agents/ pins its own (D241, D281), with an effort the harness
    parses (an unknown one silently falls back to the model's default).
    The read-only roles (reader, scout: one deny list) can't reach the
    Ghidra MCP's write tools: the bridge's default port is the owner's live
    Ghidra. The builder spawns and messages no seat (Agent, SendMessage).
    Only the builder, whose seats wait on suites and sittings, keeps its
    prompt cache an hour."""
    roles, heads = {}, {}
    for path in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        heads[path.stem] = head = path.read_text(encoding="utf-8").split("---\n")[1]
        roles[path.stem] = dict(re.findall(r"^(\w+): (.*)$", head, re.M))
    assert {stem: (f.get("name"), f.get("model"), f.get("effort")) for stem, f in roles.items()} == {
        stem: (stem, *pin) for stem, pin in ROLES.items()}
    denied = {stem: set(f["disallowedTools"].split(", ")) for stem, f in roles.items()}
    assert denied["azurik-scout"] == denied["azurik-reader"] >= {
        "Edit", *(f"mcp__ghidra__{t}" for t in GHIDRA_WRITERS)}
    assert {"Edit", "Write", "mcp__ghidra"} <= denied["azurik-mechanic"]
    assert {"Agent", "SendMessage"} <= denied["azurik-builder"]
    assert {s for s, h in heads.items() if "\nexperimental:\n  cacheTtl: 1h\n" in h} == {"azurik-builder"}


def test_the_roles_gate_with_agents_mds_gate_and_load_only_skills_tracked_here():
    """A role's commands work on AzurKit: the builder gates with AGENTS.md's
    gate. ``$EV/tools/land`` and its queue resolve branches and receipts in
    Modkit until Step 4.16b teaches them AzurKit, and ``waitfor`` finds a
    receipt by key only there (by its path, anywhere), so no role names the
    queue or waits on a key. Each skill a role says to load is one tracked
    in .claude/skills/; one not ported yet is read from Modkit."""
    gate = re.search(r"\*\*The gate:\*\* run `([^`]+)`", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    bodies = {path.stem: " ".join(path.read_text(encoding="utf-8").split("---\n", 2)[2].split())
              for path in sorted((ROOT / ".claude" / "agents").glob("*.md"))}
    assert " ".join(gate.group(1).split()).replace("<worktree>", "<lane>") in bodies["azurik-builder"]
    assert not [s for s, body in bodies.items() if re.search(r"\$EV/tools/land\b|queue:|waitfor[^`]*<key>", body)]
    skills = {Path(rel).parent.name for rel in tracked(".claude/skills") if rel.endswith("/SKILL.md")}
    assert {name for body in bodies.values() for name in re.findall(r"\bload `([\w-]+)`", body)} <= skills


def test_no_skill_holds_text_the_skill_loader_runs_as_a_shell_command():
    """Claude Code's Skill tool runs a "!" plus a backtick-quoted span
    (after whitespace) and a fence opened by three backticks and "!" as
    shell commands before the skill loads, and a failing command fails the
    load: a quoted pytest banner ending in " !" plus a backtick kept one of
    Modkit's skills from loading. The guard refuses any "!" directly before
    a backtick, a superset of both of the loader's patterns (Claude Code
    2.1.296), in every line of every tracked skill."""
    skills = [rel for rel in tracked(".claude/skills") if rel.endswith(".md")]
    hits = [f"{rel}:{n}: {line.strip()}"
            for rel in skills
            for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r"!`|```!", line)]
    assert skills and not hits, (
        "the Skill tool runs this text as a shell command, so the skill fails to load; "
        "reword it so no '!' sits directly before a backtick:\n" + "\n".join(hits))


def test_no_tracked_text_holds_a_home_path_and_no_doc_cites_a_dated_evidence_folder():
    """The repo goes public (D951): tracked text names the private evidence
    folder as ``$EV`` and a checkout's files by relative paths, never a
    home path: the running user's home written out, or the owner's layout
    under a home folder (HOME_LAYOUT). Nor do the docs and skills (every
    tracked ``.md``) cite one step's dated evidence folder (DATED_EVIDENCE).
    Binary files are skipped. What only
    ``scripts/oracle_sync.py`` writes is Modkit's text until its next sync
    (``tests/oracle/`` and the source ORACLE.toml pins): a hit there is
    fixed in Modkit. A hit prints its file, line and the match alone."""
    oracle = tomllib.loads((ROOT / "tests" / "oracle" / "ORACLE.toml").read_text(encoding="utf-8"))
    synced = {rel for family in oracle.values() if isinstance(family, dict) for rel in family.get("source", {})}
    home = str(Path.home()).rstrip("/\\")
    own_home = re.compile(re.escape(home) + r"[/\\]") if len(home) > 3 else None
    hits = []
    for rel in tracked():
        if rel.startswith("tests/oracle/") or rel in synced:
            continue
        data = (ROOT / rel).read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for pattern in (HOME_LAYOUT, own_home, DATED_EVIDENCE if rel.endswith(".md") else None):
            for m in pattern.finditer(text) if pattern else ():
                hits.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {m.group()}")
    assert not hits, "name $EV or a relative path instead:\n" + "\n".join(hits)
