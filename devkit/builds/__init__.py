"""the build checks: what each pack's sites hold in any build's XBE, and the physics sliders' values

Modkit's ``azurik-mod verify-patches`` and ``inspect-physics``, ported in
Step 4.6l; each verb's reference is ``devkit/builds/README.md``."""

VERBS = {
    "verify-patches": "each pack's sites in a build's XBE: applied, vanilla or drifted, and any byte outside them",
    "inspect-physics": "what each player_physics slider site and walk's config.xbr cell of a build hold",
}
