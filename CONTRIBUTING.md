# Contributing

Python 3.13 or newer, managed by `uv`. Use the `make` targets, not the raw
tools. [CLAUDE.md](CLAUDE.md) explains how the repository checks itself, and
[docs/WORKFLOW.md](docs/WORKFLOW.md) is how work moves from an issue to a
merged pull request.

```bash
uv sync
```

```bash
make lint
```

```bash
make type
```

```bash
make test
```

```bash
make check
```

`make check` runs lint, type, test and the five gates on this package. On a
clean `main` the gates see no touched files and pass. To check a branch the
way CI does, pass the merge-base SHA to every gate:

```bash
make check OO_BASE="--base-ref $(git merge-base origin/main HEAD) --require-base" COUPLING_BASE="--base-ref $(git merge-base origin/main HEAD) --require-base" SUPPRESSION_BASE="--base-ref $(git merge-base origin/main HEAD) --require-base" LAYERS_BASE="--base-ref $(git merge-base origin/main HEAD) --require-base" DESIGN_BASE="--shadow-check $(git merge-base origin/main HEAD)"
```

After a change under `src/oo_ratchet/`, rewrite the baselines and commit them
with the source:

```bash
make update-oo
```

```bash
make update-coupling
```

Run one test class or tier:

```bash
uv run pytest tests/test_oo_cli.py::TestOptionsParse -m ""
```

```bash
uv run pytest -m slow
```

```bash
uv run pytest tests/test_design_evals.py
```

The docs are checked by `tests/test_docs_structure.py` and
`tests/test_readme_guide.py`, which run in `make test`. Every command in
`docs/CONFIGURING.md` must name a real gate and flags that gate accepts.
