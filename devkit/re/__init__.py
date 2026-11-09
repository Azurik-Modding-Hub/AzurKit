"""the reverse-engineering tools: offline XBE reads, shim authoring and the Ghidra side

Each verb's reference is ``devkit/re/README.md``."""

VERBS = {
    "xbe": "offline reads of a default.xbe: addresses, values, strings, floats, references and listings",
    "plan-trampoline": "size a hook site: the instructions a trampoline replaces and whether it ends on a boundary",
    "shim-inspect": "a compiled shim object's sections, symbols and relocations, its calls at a release's addresses",
    "new-shim": "scaffold a shim pack (its module and C entry) and print the hand edits left",
    "test-for-va": "the tests that pin a VA or a pack (spelled, the facts and goldens, its importers), --run runs them",
    "region-map": "check Europe's address map against both images, or find a USA address's Europe twin",
    "node-types": "check or write the shipped node_types.json from both images' node-type registrations",
    "ghidra-serve": "serve a read-only copy of a Ghidra project headlessly (start, status, stop)",
    "ghidra-query": "decompile, disassemble or list the references to a VA in a ghidra-serve copy (read-only)",
    "ghidra-sync": "rename and annotate a live Ghidra's functions from the facts, the anchors and the packs",
    "ghidra-snapshot": "dump a live Ghidra's function, label and struct names to JSON (data/ghidra_snapshot.json)",
    "struct-diff": "the structs of data/structs.h against a live Ghidra's",
    "ghidra-apply": "a reviewed plan dry-run on a copy of a Ghidra project, or written into the closed project",
    "ghidra-backup": "list, restore or prune ghidra-apply's backups of a project",
}
