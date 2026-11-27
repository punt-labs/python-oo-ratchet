# REVIEW.md

Instructions for every reviewer of this repository: Devin Review, Qodo, the
local review agents (`code-reviewer`, `silent-failure-hunter`), and automated
security review. Read this before raising a finding.

`oo-ratchet` is a set of quality gates that adopter repositories (vox, quarry,
lux, z-spec) run in CI. Its job is to fail a change that makes code worse and
to say plainly why. A gate that passes what it should fail is the worst defect
this repository can ship, because every adopter trusts the verdict.

## What we want flagged

- A gate that passes a regression it should catch, or fails a change it
  should pass.
- Fail-open paths: an unreadable baseline, a git error, a parse error or an
  unresolvable base that ends in a pass instead of a failure or exit 2.
- A baseline or audit write that can lose rows, corrupt the file, or loosen a
  recorded metric outside the audited operations (`--relax`,
  `--rebaseline-files`, `--rebaseline`).
- A change to the baseline or audit file formats that adopter repos would
  read differently.
- A metric computed differently from what `docs/REFERENCE.md` documents.
- Errors swallowed or logged without reaching the exit status or the report.
- Changed behavior with no test, or a test that cannot fail.
- Security defects in the code: shell or argument injection into git calls,
  paths that escape the repository, unsafe deserialization.

## Out of scope

- **`.claude/settings.json`.** Its permission allow-list is the operator's
  deliberate choice, set broad so agents can work without constant prompts.
  Do not raise findings about how broad its permissions are, and do not
  suggest narrowing them.
- Anything CI enforces: ruff format and lint, mypy and pyright strict, and
  this repository's own OO, coupling and suppression ratchets.
- Lines the pull request did not change.
- `__new__` as the constructor. It is the standard here.
- Suppressions (`# noqa`, `# type: ignore`, `xfail`). Never suggest them.
- PR titles, descriptions, commit messages and CHANGELOG wording.
- Agent process documents: `CLAUDE.md`, `docs/WORKFLOW.md` and
  `.punt-labs/**`. They describe how agents work this repository and are not
  code. A finding on them is in scope only when the text states something
  false about the code it describes.
- The `evals/design/*/bad` packages. They contain design smells on purpose.

## Severity

- Important: a gate that wrongly passes or fails, a fail-open path, a lost or
  corrupted baseline, a crash, an in-scope security defect.
- Nit: everything else. At most five per pull request; group similar
  findings into one summary.
