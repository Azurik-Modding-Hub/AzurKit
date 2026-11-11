"""The agents' files: each role in ``.claude/agents/`` pins its model, each
tracked skill's frontmatter names its folder and the skills hold no text
the Skill tool runs as a shell command, and no
tracked text holds a home path or cites the private evidence folder but
its tools.

The roles and skills are tracked here under their ``azurik-*`` names
(D951); the first two guards are Modkit's (``tests/test_retired_names.py``),
ported with the four roles then in use; the judge returned on Fable 5.2 (D1207)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# D281 (amending D241): each role on the model that fits its job; Opus at xhigh where judgment is the job,
# Sonnet for a lookup with cites, Haiku for a handed-over command list; Fable at xhigh for a round's single designer
# and a hard root-cause hunt (D1207, amending D457 for those seats only).
ROLES = {"azurik-builder": ("opus", "xhigh"), "azurik-reader": ("opus", "xhigh"), "azurik-judge": ("fable", "xhigh"),
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
#: A cite of anything in the private evidence folder but its tools (``$EV/tools/``, what the seats run, the
#: folder's interface): a dead link in the public repo, so a sitting, a step or a measurement is named in words.
EV_CITE = re.compile(r"\$EV" r"/(?!tools/)[^\s`'\"),;\]]*")
#: The one cite left, and where: w3's barrier's reason, a value ``db_digest`` hashes into every plan (so into
#: ``tests/goldens/rando_plans.json``), reworded with the database's next change; in w3's level file and in the
#: authoring that writes it (``python -m devkit rando author``), one value.
HASHED = {"src/azurkit/tools/randomizer/data/levels/w3.toml": "override_reason = ",
          "devkit/rando/draft/authoring/w3.toml": "override_reason = "}


def tracked(*pathspec: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--cached", "-z", *pathspec],
                         capture_output=True, text=True, check=True).stdout
    return [rel for rel in out.split("\0") if rel and (ROOT / rel).is_file()]


def test_every_agent_role_pins_the_model_that_fits_its_job():
    """An unpinned seat runs the session's model, so each role in
    .claude/agents/ pins its own (D241, D281), with an effort the harness
    parses (an unknown one silently falls back to the model's default).
    The read-only roles (reader, judge, scout: one deny list) can't reach the
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
    assert denied["azurik-scout"] == denied["azurik-judge"] == denied["azurik-reader"] >= {
        "Edit", *(f"mcp__ghidra__{t}" for t in GHIDRA_WRITERS)}
    assert {"Edit", "Write", "mcp__ghidra"} <= denied["azurik-mechanic"]
    assert {"Agent", "SendMessage"} <= denied["azurik-builder"]
    assert {s for s, h in heads.items() if "\nexperimental:\n  cacheTtl: 1h\n" in h} == {"azurik-builder"}


def test_the_roles_gate_with_agents_mds_gate_and_load_only_skills_tracked_here():
    """A role's commands work on AzurKit: the builder gates with AGENTS.md's
    gate. ``$EV/tools/land`` and its queue work on Modkit until Step 4.17's
    switch, so no role names the queue; a gate seat returns its key and ends
    (``waitfor`` finds AzurKit's keys since Step 4.16b, for the orchestrator),
    so no role waits on a key. Each skill a role says to load is one tracked
    in .claude/skills/ (every one of Modkit's is, since Step 4.16a2)."""
    gate = re.search(r"\*\*The gate:\*\* run `([^`]+)`", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    bodies = {path.stem: " ".join(path.read_text(encoding="utf-8").split("---\n", 2)[2].split())
              for path in sorted((ROOT / ".claude" / "agents").glob("*.md"))}
    assert " ".join(gate.group(1).split()).replace("<worktree>", "<lane>") in bodies["azurik-builder"]
    assert not [s for s, body in bodies.items() if re.search(r"\$EV/tools/land\b|queue:|waitfor[^`]*<key>", body)]
    skills = {Path(rel).parent.name for rel in tracked(".claude/skills") if rel.endswith("/SKILL.md")}
    assert {name for body in bodies.values() for name in re.findall(r"\bload `([\w-]+)`", body)} <= skills


def test_every_skill_loads_its_frontmatter_naming_its_folder_and_no_text_the_loader_runs_as_a_shell_command():
    """Claude Code lists a skill by its SKILL.md's frontmatter: each tracked
    skill's folder holds one that opens with a ``---`` block whose ``name``
    is the folder's and whose ``description`` (inline, or a folded block's
    indented lines) says when to load it (Step 4.16a2's seven skills).
    And its Skill tool runs a "!" plus a backtick-quoted span (after
    whitespace) and a fence opened by three backticks and "!" as shell
    commands before the skill loads, and a failing command fails the load:
    a quoted pytest banner ending in " !" plus a backtick kept one of
    Modkit's skills from loading. The guard refuses any "!" directly before
    a backtick, a superset of both of the loader's patterns (Claude Code
    2.1.296), in every line of every tracked skill."""
    skills = [rel for rel in tracked(".claude/skills") if rel.endswith(".md")]
    heads = {}
    for rel in skills:
        if Path(rel).name == "SKILL.md":
            text = (ROOT / rel).read_text(encoding="utf-8")
            head = text.split("---\n", 2)[1] if text.startswith("---\n") and text.count("---\n") > 1 else ""
            name = re.search(r"^name: *(\S+) *$", head, re.M)
            said = re.search(r"^description: *(.*)\n((?:[ \t]+\S.*\n)*)", head, re.M)
            heads[Path(rel).parent.name] = (name and name.group(1),
                                            bool(said and (said.group(1).strip(" >-|") or said.group(2).strip())))
    assert heads == {folder: (folder, True) for folder in {Path(rel).parts[2] for rel in skills}}
    hits = [f"{rel}:{n}: {line.strip()}"
            for rel in skills
            for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1)
            if re.search(r"!`|```!", line)]
    assert skills and not hits, (
        "the Skill tool runs this text as a shell command, so the skill fails to load; "
        "reword it so no '!' sits directly before a backtick:\n" + "\n".join(hits))


def test_no_tracked_text_holds_a_home_path_or_cites_the_private_evidence_folder():
    """The repo is public (D951, D1024): tracked text names the private
    evidence folder as ``$EV`` and a checkout's files by relative paths,
    never a home path: the running user's home written out, or the owner's
    layout under a home folder (HOME_LAYOUT: its Documents folder among them).
    Nor does it cite anything in ``$EV`` but its tools (EV_CITE): a code
    comment, a data file's note or a doc names what a claim rests on (a
    sitting, a step, a measurement) in plain words (Step 4.4pub2), but the
    one value the plans hash (HASHED). Binary files are skipped, and
    nothing else: the files ported from Modkit are AzurKit's own (the sync
    ended, Step 4.12b). A hit prints its file, line and the match alone."""
    home = str(Path.home()).rstrip("/\\")
    own_home = re.compile(re.escape(home) + r"[/\\]") if len(home) > 3 else None
    hits = []
    for rel in tracked():
        data = (ROOT / rel).read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for pattern in (HOME_LAYOUT, own_home, EV_CITE):
            for m in pattern.finditer(text) if pattern else ():
                start = text.rfind("\n", 0, m.start()) + 1
                if pattern is EV_CITE and rel in HASHED and text.startswith(HASHED[rel], start):
                    continue
                hits.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {m.group()}")
    assert not hits, "name $EV, a relative path or what a claim rests on in words instead:\n" + "\n".join(hits)


#: A Markdown link's target, ``[text](target)``, read with its code spans blanked and its fences skipped.
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
#: Modkit's checkout as a place to read (D1171 deletes it): its variables, a link into its package, an import.
MODKIT = re.compile(r"\$\{?(?:AZURKIT_)?MODKIT\b|\.\./azurik_mod/|\bpython -m azurik_mod\b|\b(?:from|import) azurik_mod\b")


def test_every_relative_link_in_tracked_markdown_reaches_a_tracked_file_and_no_text_points_into_modkit():
    """Modkit's checkout is deleted and its history is a private archive
    (D1171, D1030), so tracked text names it as provenance, in words, and
    nothing here reads it (Step 4.24d): each relative link of a tracked
    Markdown file (its code spans and fences aside) reaches a tracked file
    or folder of this checkout, and no tracked text names Modkit's checkout
    by its variables, links into its package or imports it (``MODKIT``). A
    hit prints its file, line and target."""
    files = tracked()
    paths = set(files) | {parent.as_posix() for rel in files for parent in Path(rel).parents}
    root = ROOT.resolve()
    hits = []
    for rel in files:
        data = (ROOT / rel).read_bytes()
        if b"\0" in data:
            continue
        lines = data.decode("utf-8", errors="replace").splitlines()
        hits += [f"{rel}:{n}: {m.group()}" for n, line in enumerate(lines, 1) for m in MODKIT.finditer(line)]
        if not rel.endswith(".md"):
            continue
        fenced = False
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            for m in () if fenced else LINK.finditer(re.sub(r"`+[^`\n]*`+", "x", line)):
                target = m.group(1).partition("#")[0]
                if not target or re.match(r"[a-z][a-z0-9+.-]*:", target):
                    continue
                at = ((ROOT / rel).parent / target).resolve()
                if not at.is_relative_to(root) or at.relative_to(root).as_posix() not in paths:
                    hits.append(f"{rel}:{n}: {m.group(1)}")
    assert not hits, "point it at this checkout's file, or name Modkit's in words, not as a link or a path:\n" + (
        "\n".join(hits))


# --- Step 4.28f: Modkit's retired-names guard, ported ------------------------------------------------------------

#: A name Modkit retired (a regex, matched case-sensitively: ``XDVDFS``, the Xbox file system, stays) -> why: kept out
#: of AzurKit's live docs and skills, which lanes still port from Modkit's. Modkit's list, but its config-mod files'
#: ``registry.json`` and ``entity_values.json``, which AzurKit names to refuse them (``edits/modkit_retired.json``).
#: The game-data repo's old paths and the xdvdfs env var are split so a ``git grep`` for either finds no live use.
RETIRED = {
    r"xdvdfs": "Modkit's Step 1.24b: every build reads and packs images with its own XISO code (D25, D30)",
    r"AZURIK_" r"XDVDFS": "Modkit's Step 1.24b: the xdvdfs locator, downloader and their env var are deleted",
    r"(?:MichaelJSr|Azurik-Testing)/" r"AzurKit-gamedata":
        "the game-data repo is Azurik-Modding-Hub/AzurKit-gamedata since 2026-11-01 (D1028)",
    r"compile\.sh": "Modkit's Step 1.28: zig builds every shim (Q37)",
    r"new_shim\.sh": "Modkit's Step 1.28: the scaffolder replaced the script (Q37)",
    r"\bAZURIK_VANILLA_(?:XBE|GAMEDATA)\b|\bAZURIK_GAMEDATA\b":
        "Modkit's Step 1.4b: one resolver finds the vanilla image (AZURKIT_ISO)",
    r"ghidra_plugin\b": "Modkit's Step 2.13a-ii: the GhydraMCP fork is deleted; stock Ghydra",
    r"\bGHIDRA_DEFAULT_PORT\b": "Modkit's Step 2.13a-ii: the MCP server's Ghidra half is deleted (AZ-034)",
    r"\bAZURIK_GHIDRA_\w+": "Modkit's Step 2.13a-ii: one Ghidra client, port 8193 or --port (AZ-034)",
    r"\bAZURIK_DECOMP_CACHE\b": "Modkit's Step 2.13a-ii: decomp_cache is deleted",
    r"azurik-mod xrefs\b|`xrefs`": "Modkit's Step 2.13a-ii: the xrefs verb is dropped (Q81)",
    r"\bcall-graph\b": "Modkit's Step 2.13a-ii: the call-graph verb is dropped (Q81)",
    r"\bdecomp-cache\b": "Modkit's Step 2.13a-ii: the decomp-cache verb is dropped (Q81)",
    r"\bghidra-coverage\b": "Modkit's Step 2.13a-ii: the ghidra-coverage verb is dropped (Q81)",
    r"\b(?:decomp_cache|re_recorder|call_graph|xref_aggregator|ghidra_coverage|scan_ghidra_hexdump)\b":
        "Modkit's Step 2.13a-ii: dropped modules (Q50)",
    r"\bINDEX\.md\b": "Modkit's Step 3.1: the doc index is gone",
    r"\bAGENT_GUIDE\.md\b|\bONBOARDING\.md\b": "Modkit's Step 3.1: its CLAUDE.md and CONTRIBUTING.md replaced them",
    r"\bSHIM_AUTHORING\.md\b": "Modkit's Step 3.3c: docs/SHIMS.md is the one shim doc",
    r"\bMODDING_GUIDE\.md\b": "Modkit's Step 3.3c: its tools doc held the mod-file format",
    r"\bLEARNINGS\.md\b|\bDECOMP\.md\b": "Modkit's Step 3.3d: docs/RE_MOVEMENT.md, RE_DATA.md and RE_XBE.md",
    r"\b(?:LOADING_ZONES_AUDIT|RANDOMIZER_AUDIT|TOOLING_ROADMAP|TOOLS_UPKEEP|D1_EXTEND)\.md\b|\bFUTURE_PASSES\b":
        "Modkit's Steps 3.3a, 3.3c and 3.3d archived them",
    r"--index-xbr\b": "Modkit's Step 2.16l (AZ-217): audio dump names waves from the XBR's own table",
    r"\bapprove\.yml\b": "Modkit's Step 2.20c: D5's approval was a step of its policy workflow",
    r"\brandomize-gems\b|azurik-mod randomize(?![-\w])|\bcmd_randomize(?:_gems)?\b":
        "Modkit's Step 2.23a (D133): randomize-full covered both verbs",
    r"--(?:no-major|no-keys|no-gems|no-barriers|hard-barriers|no-connections|item-pool)\b":
        "Modkit's Step R1.10b (Q287, D43): the randomizer's settings replaced the pool flags",
    r"\brand_(?:major|keys|gems|barriers|connections)\b":
        "Modkit's Step R1.10b (Q287, D43): the five pool packs are retired for the randomizer's settings",
    r"--player-character-standardize\b|\bplayer_character_standardize\b":
        "Modkit's Step 2.73a (D43, D133): the garret4 mode replaced it",
    r"--player-character-mode (?:\w+\|)*full\b|\bFully the model\b":
        "Modkit's Step 2.129 (D329): own (Balanced) replaced the mode full",
}


def test_live_docs_and_skills_never_mention_retired_names():
    """Modkit's REORG_PLAN §6a.6 guard: no tracked Markdown file but the
    archive and the developer log (histories) names a retired name
    (:data:`RETIRED`), outside its ``## History`` sections (up to the next
    ``#`` or ``##`` heading outside a code fence; a ``# comment`` in a
    fenced shell block is no heading). A step that retires a name adds it
    and rewrites the docs in the same change."""
    pattern = re.compile("|".join(f"(?:{p})" for p in RETIRED))
    hits = []
    for rel in tracked("*.md", ":!docs/archive/", ":!docs/DEVLOG.md", ":!docs/devlog/"):
        history = fence = False
        for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fence = not fence
            elif not fence and re.match(r"#{1,2} ", line):
                history = line.rstrip() == "## History"
            if not history and (m := pattern.search(line)):
                hits.append(f"{rel}:{n}: {m.group()}")
    assert not hits, "retired names (see RETIRED) in live docs:\n" + "\n".join(hits)
