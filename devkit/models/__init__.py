"""the model verbs ModelKit's adapter calls: a variant dressed as a build dresses it, a body inspected,
exported as glTF, its edits checked and imported, previewed in headless Blender or edited in Blender through
to a built image; the fx graphs read, planned and cloned; the arm turns that keep a held prop out of a body's chest

Each verb's reference is ``devkit/models/README.md``."""

VERBS = {
    "model": "a character body's leafs: dress a variant as a build does, inspect a body, export it as glTF 2.0 "
             "(a variant's textures as PNGs), check and import an edited glTF and its clips, list its chains, "
             "preview and pose its springs, rest its mesh at other values, preview it in headless Blender, "
             "edit it in Blender through to a built image",
    "fx": "the fx graphs' leafs: list, show, closure, texture, templates, plan (a variant's clone) and clone",
    "blender-check": "the Blender batch on the real Blender (headless, a made-up body, no game data)",
    "weapon-fit": "W35's arm fit: the turn of both arms in each of Garret's staff moves that keeps a body's prop out "
                  "of its chest, as weapons.json's fits rows (--write)",
}
