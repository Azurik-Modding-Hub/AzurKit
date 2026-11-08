"""Blender for the model verbs, always headless (``--background
--factory-startup``): :mod:`.batch` draws many frames of one body from one
Blender and holds the machine's Blender slots; :mod:`.batch_inside` and
:mod:`.preview` run inside Blender (``blender --python FILE -- JOB``) and are
never imported but for :data:`.preview.VIEWS`."""
