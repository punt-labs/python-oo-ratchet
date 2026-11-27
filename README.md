# oo-ratchet

> Quality gates for Python code that fail when a change makes it worse.

[![License](https://img.shields.io/github/license/punt-labs/python-oo-ratchet)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/punt-labs/python-oo-ratchet/ci.yml?label=CI)](https://github.com/punt-labs/python-oo-ratchet/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/punt-oo-ratchet)](https://pypi.org/project/punt-oo-ratchet/)
[![Python](https://img.shields.io/pypi/pyversions/punt-oo-ratchet)](https://pypi.org/project/punt-oo-ratchet/)

`oo-ratchet` is a command line tool that runs five checks over a Python
package. Most of them are ratchets: a ratchet compares the code with a
baseline recorded earlier and fails if quality got worse. A baseline is a
JSON file, committed to the repository, that holds the scores of each file.
The tool is the shared copy of gates that vox, quarry, lux and z-spec each
used to keep in their own `tools/` directory.

## Quick Start

The tool needs Python 3.13 or newer.

```bash
uv add --dev punt-oo-ratchet
```

Record today's scores for a package as the first baseline:

```bash
uv run oo-ratchet oo src/pkg/ --update
```

Check a change against that baseline:

```bash
uv run oo-ratchet oo src/pkg/ --check
```

<details>
<summary>Other ways to install</summary>

With pip:

```bash
pip install punt-oo-ratchet
```

Without installing, with uvx:

```bash
uvx --from punt-oo-ratchet oo-ratchet --help
```

</details>

<details>
<summary>Verify the install</summary>

```bash
uv run oo-ratchet --help
```

The output names the five gates: `oo`, `coupling`, `suppressions`, `design`
and `layers`.

</details>

## Features

- **OO metrics** --- scores each file on encapsulation, parameter counts,
  complexity, module size and a few conventions, and requires at least one
  score to improve on every touched file
- **Coupling and cohesion** --- counts imports between modules, import
  cycles and how little the methods of a class share their fields, and fails
  on any regression
- **Suppression count** --- counts `noqa`, `type: ignore`, `pylint: disable`
  and `pyright: ignore` comments and fails when the total rises
- **Layer rules** --- checks that modules import only from their own layer or
  one nearer the core, with a baseline of known violations that can only
  shrink
- **Design check** --- reports design smells such as classes that are only a
  bag of functions; opt in to fail on a small set of reliable rules
- **Audited exceptions** --- loosening a baseline needs a named command and
  leaves a row in an audit log
- **Fails closed** --- an unreadable baseline, a git error or an unresolvable
  base commit fails the run

## What It Looks Like

A branch adds a class with an explicit `__init__` and one `noqa` comment. The
`oo` gate reports the regressions and exits 1. Rows for metrics that passed
are left out here:

```text
$ oo-ratchet oo src/shop/ --check --base-ref origin/main --require-base
File                                     Metric                       Baseline    Current    Delta     Status
------------------------------------------------------------------------------------------------------------
src/shop/application/checkout.py         encapsulation_ratio             1.000      0.000   -1.000  REGRESSED
src/shop/application/checkout.py         init_violations                 0.000      1.000   +1.000  REGRESSED
src/shop/application/checkout.py         public_attr_violations          0.000      1.000   +1.000  REGRESSED
FAIL: baseline out of date -- run make update-oo: src/shop/application/checkout.py
FAIL: regression detected
FAIL: no metric improved on any touched file
```

The `suppressions` gate fails on the same branch:

```text
$ oo-ratchet suppressions src/shop/ --check --base-ref origin/main --require-base
Baseline total: 0
Current total:  1

FAIL: suppression count increased by 1 (after waivers)

Files with new or increased, unwaived suppressions:
  src/shop/application/checkout.py: +1 unwaived (0 -> 1)
```

## Commands

Run `oo-ratchet <gate> <package-dir> [flags]`. The package directory is the
folder that holds `__init__.py`.

| Gate | What it does | Main flags |
|------|--------------|------------|
| `oo` | Must-improve: no metric regresses on a touched file and at least one improves | `--check`, `--update`, `--relax FILE --justify`, `--rebaseline-files --reason`, `--json` |
| `coupling` | Regression-only: import counts, cycles and cohesion must not get worse | `--check`, `--update`, `--rebaseline-files --reason`, `--json` |
| `suppressions` | Regression-only: the total of lint and type-ignore comments must not rise | `--check`, `--update`, `--rebaseline --reason`, `--relax FILE --justify` |
| `layers` | A baseline of imports that break the layer rules; it may only shrink | `--check`, `--update`, `--suggest`, `--json`, `--allow-config-change` |
| `design` | Advisory report of design smells; exits 1 only with `--enforce` | `--shadow-check REF`, `--enforce`, `--layers FILE`, `--json` |

Flags that apply to most gates:

- `--check` compares the code with the baseline and exits 1 on failure.
- `--update` records the current scores and never loosens them.
- `--base-ref REF --require-base` compares against a git commit and fails if
  it cannot be found. In a pull request, pass the merge-base commit.
- `--tripwire` is for the run after a merge to `main`. The one adoption
  merge, which adds the first baseline, passes.
- `--namespace NAME` scans several directories as one package.

A ring is a named layer of the package: `entry`, `adapters`, `application` or
`domain`. A shadow check scans the code at the merge base and again at the
working tree, then reports which findings were added or removed.
`oo-ratchet <gate> --help` lists every flag.

## Setup

To use the tool in a repository, follow
[Configuring a Repo](docs/CONFIGURING.md). It covers which gates to turn on
and in what order, the `[tool.oo-ratchet]` settings in `pyproject.toml`, a
walk-through for adding layer rules, `Makefile` targets, a CI workflow, and
which files to commit.

## Documentation

[Configuring a Repo](docs/CONFIGURING.md) |
[Reference](docs/REFERENCE.md) |
[Layers Gate](docs/LAYERS.md) |
[Design Check](docs/DESIGN.md) |
[Formal Model](docs/ratchet.tex) |
[Policy](https://github.com/punt-labs/punt-kit/blob/main/lang-rules/python/python-oo-adoption.md) |
[Contributing](CONTRIBUTING.md) |
[Changelog](CHANGELOG.md)

## License

MIT
