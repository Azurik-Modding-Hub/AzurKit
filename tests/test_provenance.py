"""Nothing here is taken from a Modkit file that credits lines to JTCPP (D95):
no tracked or untracked text file, or gzip file's text, shares 5 or more
lines with the fingerprints of that whole list
(``tests/provenance/jtcpp_lines.txt``)."""

from __future__ import annotations

import subprocess
from pathlib import Path

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
    found = {}
    for rel in sorted(set(filter(None, listed)) - SKIP):
        data = (ROOT / rel).read_bytes() if (ROOT / rel).is_file() else b"\0"
        if (inner := _leak_guard.gunzip(data)) is not None:
            data = inner[0]
        if b"\0" not in data[:8192] and (n := shared(data.decode("utf-8", errors="replace"), prints)) >= THRESHOLD:
            found[rel] = n
    assert found == {}
