"""the reverse-engineering tools: offline XBE reads and shim authoring (the Ghidra side comes later)

Each verb's reference is ``devkit/re/README.md``."""

VERBS = {
    "xbe": "offline reads of a default.xbe: addresses, values, strings, floats, references and listings",
    "plan-trampoline": "size a hook site: the instructions a trampoline replaces and whether it ends on a boundary",
    "shim-inspect": "a compiled shim object's sections, symbols and relocations, its calls at a release's addresses",
    "new-shim": "scaffold a shim pack (its module and C entry) and print the hand edits left",
    "test-for-va": "the tests that pin a VA or a pack (spelled, the facts and goldens, its importers), --run runs them",
    "region-map": "check Europe's address map against both images, or find a USA address's Europe twin",
}
