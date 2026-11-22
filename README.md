# oo-ratchet

The Punt Labs quality ratchets for Python repos, extracted from the copies that
lived in `tools/` of vox, quarry, lux and z-spec. One installable package, one
CLI, three gates:

| Gate | Command | Rule |
|------|---------|------|
| OO metrics | `oo-ratchet oo <src> --check` | must-improve: no metric regresses on a touched file and at least one improves |
| Coupling/cohesion | `oo-ratchet coupling <src> --check` | regression-only |
| Suppressions | `oo-ratchet suppressions <src> --check` | regression-only on the total `noqa` / `type: ignore` / `pylint: disable` / `pyright: ignore` / per-file-ignores count |

Every gate compares against the baseline committed at the merge base, fails
closed when the base or baseline cannot be read, and only loosens through
audited operations (`--relax`, `--rebaseline-files`, `--rebaseline`). A
suppressions `--relax` waiver covers only the change that adds it; once it
merges it is retired, so a later cleanup is a real floor. The
policy it enforces is
[`python-oo-adoption.md`](https://github.com/punt-labs/punt-kit/blob/main/lang-rules/python/python-oo-adoption.md)
in punt-kit; the formal model is [`docs/ratchet.tex`](docs/ratchet.tex).

## Install

```bash
uv add --dev punt-oo-ratchet
```

Requires Python 3.13+. No runtime dependencies.

## Use

```make
check-oo:
	uv run oo-ratchet oo src/pkg/ --check $(OO_BASE)
update-oo:
	uv run oo-ratchet oo src/pkg/ --update $(OO_BASE)
check-coupling:
	uv run oo-ratchet coupling src/pkg/ --check $(COUPLING_BASE)
check-suppressions:
	uv run oo-ratchet suppressions src/pkg/ --check $(SUPPRESSION_BASE)
```

On PRs, pass the merge-base SHA: `--base-ref "$(git merge-base origin/main HEAD)"
--require-base` (an explicit ref is compared as given, so `origin/main` itself
would pull in later main changes). On the post-merge `push: [main]` run, pass
`--base-ref HEAD~1 --require-base --tripwire` to every gate so the one-time
adoption merge bootstrap-passes. `oo-ratchet <gate> --help` lists each gate's
flags. Baseline and audit files (`.oo-baseline.json`, `.oo-audit.jsonl`,
`.oo-coupling-baseline.json`, ...) keep the same names as the embedded copies,
so a repo switches over without rebaselining.

### Advisory design check

`oo-ratchet design src/pkg/ [--json]` reports OO design smells the metric
gates cannot see: stateless classes with one public method (a function wearing
a class) or several (a namespace of free functions), getter-heavy classes, and
stateful concrete classes imported across top-level subpackages instead of a
Protocol/ABC. It has no baseline and always exits 0; it is not part of
`make check`.

## Configure

Optional per-repository settings live in `pyproject.toml`; with none the strict
defaults apply. Unknown keys, metrics or modes are an error, not ignored.

```toml
[tool.oo-ratchet.coupling]
# "dataclass" (default): LCOM skips only @dataclass / __slots__ = () classes
# that store no instance state. "any": skip every class that never writes a
# private self._* attribute (object/super()/type(self).__setattr__ count).
stateless-values = "any"

[tool.oo-ratchet.coupling.caps]
# Exact repository-relative paths; a cap replaces that metric's default target
# for that one file (here a wiring hub whose job is importing many modules).
"src/pkg/facade.py" = { efferent_coupling = 20 }
```

`oo-ratchet coupling <src> --rebaseline-files a.py,b.py --reason "<why>"` is the
coupling counterpart of the OO bless: each named file is recorded unless a
metric is both over its cap (configured caps included) and worse than its
baseline; refused files are listed and not written, and the bless is audited
and waives exactly those deltas at the next `--check`.

`oo-ratchet suppressions <src> --rebaseline --reason "<why>" [--source PL-123]`
resets the suppression baseline to the current counts. It's the one write that may
raise the total (for example after a package upgrade changes the counter), and it
is audited.

## Provenance

Seeded from vox (`tools/oo_ratchet`, `tools/coupling`, `tools/suppression`),
then merged:

- **quarry**: extraction provenance for new zero-class modules (`diffmodel.py`,
  `provenance.py`), coupling `--tripwire`, `tokenize`-based suppression scan.
- **lux**: `--rebaseline-files` bounded bless with over-cap carry (`bless.py`),
  vanished-row cleanup on `--update`, removed rows recorded in the audit log;
  in 0.2.0 the broad stateless-value LCOM exemption, exact-path coupling caps
  (as `[tool.oo-ratchet.coupling]` config) and coupling `--rebaseline-files`.
- **new here**: unreadable or non-UTF-8 files become error rows instead of
  crashing the OO scorer (PL-778).

## Develop

```bash
uv sync
make check   # ruff, mypy, pyright (tests), full pytest suite
```
