# Notices and credits

## JTCPP (Jett Tripp): Elemental_Games_Modding

AzurKit is the rewrite of Azurik_Modkit, which grew out of a fork of Jett
Tripp's (JTCPP's)
[Elemental_Games_Modding](https://github.com/JTCPP/Elemental_Games_Modding).
Its randomizer tool (`tools/randomizer/`, commits `b487012` "Randomizer Tool
0.1.0" and `696fc70` "v0.2.0 Entity editor improvements", March 2026) is where
Modkit's item solver and logic database, the `config.xbr` table reader and
property schema, the level shufflers, the randomizer commands and the entity
editor started. Thank you, JTCPP.

That repository has no licence file: its README states an MIT intent and links
a `LICENSE` that isn't there. So none of his code is ported here until he
grants it, and nothing in AzurKit is taken from a Modkit file that credits his
lines: Modkit's `NOTICE.md` lists those files, and the ones since removed.
[`tests/test_provenance.py`](tests/test_provenance.py) checks every tracked text
file against line fingerprints of that whole list
([`tests/provenance/jtcpp_lines.txt`](tests/provenance/jtcpp_lines.txt), sha256s,
not the lines; written by
[`scripts/provenance_fingerprints.py`](scripts/provenance_fingerprints.py)).
The parts he started, among them the keyed `config.xbr` cells, are written new
from the format.
