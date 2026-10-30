"""Nothing here is taken from a Modkit file that credits lines to JTCPP (D95):
no tracked or untracked text file, or gzip file's text, shares 5 or more
lines with the fingerprints of that whole list
(``tests/provenance/jtcpp_lines.txt``). A file the oracle sync installed
from Modkit (``scripts/oracle_sync.py``'s ``SOURCES``, each pinned by its
sha256 in ``tests/oracle/ORACLE.toml``) is judged by the Modkit file it
ports, which may not be one of that list: Modkit's own code shares lines
with the credited files' own (``cli.py`` repeats the player model's
messages), and Modkit's NOTICE.md finds no other file holding 5 of his."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import oracle_sync
from scripts import provenance_fingerprints as fp
from tests import _leak_guard

ROOT = Path(__file__).resolve().parent.parent
THRESHOLD = 5   # Modkit's NOTICE.md: a file sharing 5 or more of his lines holds his code
SKIP = {"tests/provenance/jtcpp_lines.txt"}


def shared(text: str, prints: set[str]) -> int:
    return sum(fp.fingerprint(line) in prints for line in fp.lines(text))


def test_no_file_shares_five_lines_with_the_files_that_credit_jtcpp():
    prints = fp.read()
    assert len(prints) > 10_000
    assert shared('def x():\n    """' + "word " * 10 + '"""\n', prints) == 0
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, check=True).stdout.decode().split("\0")
    ported = oracle_sync.origins()
    assert sorted(rel for rel, origin in ported.items() if origin in fp.CREDITED) == []
    found = {}
    for rel in sorted(set(filter(None, listed)) - SKIP - set(ported)):
        data = (ROOT / rel).read_bytes() if (ROOT / rel).is_file() else b"\0"
        if (inner := _leak_guard.gunzip(data)) is not None:
            data = inner
        if b"\0" not in data[:8192] and (n := shared(data.decode("utf-8", errors="replace"), prints)) >= THRESHOLD:
            found[rel] = n
    assert found == {}
