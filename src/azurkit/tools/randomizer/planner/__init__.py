"""The randomizer v1 planner (Phase R1; REORG_PLAN §12.1's layout).

Pure stdlib: the database loader (:mod:`.loader`), the requirement grammar
(:mod:`.grammar`), the options (:mod:`.settings`), the solver's reach and
escape (:mod:`.solver`), the fill (:mod:`.fill`) and the plan file and
spoiler (:mod:`.plan`). It never imports ``randomizer/draft/``, numpy,
capstone or the ``tern`` reader (``tests/test_import_isolation.py``).
"""
