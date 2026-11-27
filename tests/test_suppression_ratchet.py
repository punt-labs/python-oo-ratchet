"""Behavior tests for the decomposed suppression counter and ratchet.

The decomposition is behavior-preserving: these lock the counting semantics
(code-line detection, category totals), the ratchet verdict (increase fails,
steady/decrease passes), and the CLI dispatch through tmp files.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import NamedTuple, Self

import pytest

from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.adapters.tallyfiles import JsonLedger, JsonTallyStore
from oo_ratchet.core.adapters.tallyformats import TallyFormat
from oo_ratchet.core.domain.errors import GitError, StateError
from oo_ratchet.core.domain.ledgers import Ceiling, Ledger
from oo_ratchet.suppression.cli import main
from oo_ratchet.suppression.patterns import FileSuppressions
from oo_ratchet.suppression.pyproject import PerFileIgnoresCounter, PyprojectError
from oo_ratchet.suppression.report import SuppressionReport
from oo_ratchet.suppression.scanner import Scanner

# Every ratchet/CLI test drives a real git init/commit/checkout sequence --
# see the marker rationale on test_oo_ratchet.py and the measured timing in
# TESTING.md.
pytestmark = pytest.mark.slow

WITH_SUPPRESSIONS = (
    "from __future__ import annotations\n\n"
    "x = 1  # noqa: E501\n"
    "y = 2  # type: ignore[assignment]\n"
    "z = 3  # pylint: disable=invalid-name\n"
)

# A multiline docstring interior and a bare comment line -- both excluded from
# the code-line scan, so their `noqa` markers must not be counted.
DOCSTRING_AND_COMMENT = '"""\n# noqa\ndocstring body\n"""\n\n# noqa\nvalue = 1\n'


class TestFileSuppressions:
    """Count suppression comments on code lines only."""

    def test_counts_code_line_suppressions(self) -> None:
        fs = FileSuppressions("m.py", WITH_SUPPRESSIONS)
        assert fs.count("noqa") == 1
        assert fs.count("type_ignore") == 1
        assert fs.count("pylint_disable") == 1
        assert fs.total == 3

    def test_docstring_and_comment_lines_excluded(self) -> None:
        assert FileSuppressions("m.py", DOCSTRING_AND_COMMENT).total == 0


class TestScanner:
    """Aggregate per-file counts into a report."""

    def test_scans_directory(self, tmp_path: Path) -> None:
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "a.py").write_text(WITH_SUPPRESSIONS)
        report = Scanner(tmp_path / "pkg", tmp_path).report
        assert report.by_category["noqa"] == 1
        assert report.by_category["type_ignore"] == 1
        assert report.total >= 2


class TestSuppressionReportRebased:
    """``rebased`` moves by_file keys onto a new root without losing counts."""

    def test_merges_on_key_collision_instead_of_overwriting(self) -> None:
        # A source file's real path can collide with a literal (non-glob)
        # per-file-ignores pattern in pyproject.toml -- e.g. a materialized
        # "/tmp/xyz/pkg/a.py" rebases onto "pkg/a.py", which is ALSO the key
        # a per-file-ignores breakdown already uses verbatim. Both entries
        # must survive the rebase merged, not one silently clobbering
        # the other.
        fs = FileSuppressions("/tmp/xyz/pkg/a.py", "x = 1  # noqa\ny = 2  # noqa\n")
        report = SuppressionReport([fs], 3, {"pkg/a.py": 3})
        rebased = SuppressionReport.rebased(report, "/tmp/xyz/pkg", "pkg")
        assert rebased.by_file == {"pkg/a.py": {"noqa": 2, "per_file_ignores": 3}}


class Result(NamedTuple):
    """The exit code and stdout lines of one CLI run."""

    exit_code: int
    lines: list[str]


class GitFixture:
    """An isolated git repo for exercising the base-commit suppression ratchet."""

    _root: Path
    _capsys: pytest.CaptureFixture[str]

    def __new__(cls, tmp: Path, capsys: pytest.CaptureFixture[str]) -> Self:
        self = super().__new__(cls)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        for key, val in (
            ("user.email", "t@example.com"),
            ("user.name", "Tester"),
            ("commit.gpgsign", "false"),
        ):
            subprocess.run(["git", "config", key, val], cwd=tmp, check=True)
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=tmp,
            check=True,
            capture_output=True,
            text=True,
        )
        self._root = Path(out.stdout.strip())
        self._capsys = capsys
        return self

    @property
    def root(self) -> Path:
        """Return the repository root."""
        return self._root

    def write_source(self, source: str) -> None:
        pkg = self._root / "pkg"
        pkg.mkdir(exist_ok=True)
        (pkg / "a.py").write_text(source)

    def run(self, *argv: str) -> Result:
        """Run the CLI on ``pkg`` and return its exit code and stdout lines."""
        self._capsys.readouterr()
        code = main(["pkg", *argv])
        return Result(code, self._capsys.readouterr().out.splitlines())

    def check(self, *, base_ref: str, require_base: bool) -> Result:
        """Run the ratchet check against ``pkg``, the fixture's scan target."""
        flags = ["--require-base"] if require_base else []
        return self.run("--check", "--base-ref", base_ref, *flags)

    def update(self, *, allow_ci_write: bool) -> Result:
        return self.run("--update", *(["--allow-ci-write"] if allow_ci_write else []))

    def relax(self, base: str, justify: str, *, allow_ci_write: bool) -> Result:
        ci = ["--allow-ci-write"] if allow_ci_write else []
        return self.run(
            "--relax", "pkg/a.py", "--justify", justify, "--base-ref", base, *ci
        )

    def write_baseline_text(self, text: str) -> None:
        (self._root / ".suppression-baseline.json").write_text(text)

    def commit(self, msg: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self._root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=self._root, check=True)
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self._root,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()


@pytest.fixture
def gfx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> GitFixture:
    fixture = GitFixture(tmp_path, capsys)
    monkeypatch.chdir(fixture.root)
    return fixture


class TestBaselineRatchet:
    """Increases fail; steady and decreases pass against the base-commit total."""

    def test_increase_fails(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")  # now 2
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("increased" in line for line in outcome.lines)

    def test_decrease_passes(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\n")  # now 1
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0
        assert any("decreased" in line for line in outcome.lines)

    def test_steady_passes(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0
        assert any("unchanged" in line for line in outcome.lines)

    def test_no_base_baseline_is_bootstrap_pass(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")  # no baseline committed
        base = gfx.commit("pre-adoption")
        outcome = gfx.check(base_ref=base, require_base=False)
        assert outcome.exit_code == 0

    def test_absent_base_unresolvable_tip_fails_closed(self, gfx: GitFixture) -> None:
        # Base commit predates the scanned pkg/ tree entirely; origin/main is
        # unresolvable and an in-tree baseline is present -> fail closed
        # UNCONDITIONALLY (no require_base), matching the OO and coupling
        # ratchets.
        (gfx.root / "README.md").write_text("placeholder\n")
        base = gfx.commit("base before pkg existed")  # pkg/ doesn't exist yet
        gfx.write_source("x = 1  # noqa\n")
        gfx.update(allow_ci_write=True)  # in-tree baseline now present
        gfx.commit("add pkg and in-tree baseline")
        outcome = gfx.check(base_ref=base, require_base=False)
        assert outcome.exit_code == 1
        assert any("origin/main" in line for line in outcome.lines)

    def test_stale_baseline_blob_does_not_false_positive(self, gfx: GitFixture) -> None:
        # A suppression comment can land in source without the committed
        # .suppression-baseline.json being refreshed in the same commit --
        # the blob then undercounts what really existed at that ref. A live
        # rescan of the base ref's real source must not report the
        # pre-existing suppression as new.
        gfx.write_source("x = 1\n")  # no suppression yet
        gfx.update(allow_ci_write=True)  # baseline total 0
        gfx.commit("pre-suppression baseline")
        gfx.write_source("x = 1  # noqa\n")  # suppression lands...
        # ...but the in-tree baseline is never refreshed to match -- it goes
        # stale at this commit, which becomes the comparison base.
        base = gfx.commit("add suppression without refreshing the baseline blob")
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0
        assert any("unchanged" in line for line in outcome.lines)

    def test_regression_line_names_the_file_at_its_real_path(
        self, gfx: GitFixture
    ) -> None:
        # Pins the rebase in _rescan_at_ref: the base-side report is scanned
        # from a tmp materialization, but the regression line printed to the
        # user must name the file at its real repo-relative path, not the
        # tmp root -- proof the by_file keys were actually rewired, not just
        # that the totals happened to match.
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("pkg/a.py: +1 unwaived (1 -> 2)" in line for line in outcome.lines)


def repo_at(root: Path) -> GitRepo:
    return GitRepo(root, ".suppression-baseline.json", ".suppression-audit.jsonl")


class TestGitRepoPathExistsAtRef:
    """``exists_at`` must distinguish real absence from any git failure."""

    def test_absent_path_is_false(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)
        assert repo.exists_at(base, "does/not/exist.py") is False

    def test_present_path_is_true(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)
        assert repo.exists_at(base, "pkg/a.py") is True

    def test_empty_path_probes_the_root_tree(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)
        assert repo.exists_at(base, "") is True

    def test_absence_message_case_does_not_matter(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Git's message casing can vary across versions/locales -- a git
        # build that capitalizes its stderr must still be recognized as
        # absence, not misread as an unrelated error.
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)

        class _UppercaseAbsence:
            returncode = 128
            stderr = "FATAL: PATH 'x.py' DOES NOT EXIST IN 'HEAD'\n"

        def _fake_run(*_args: object, **_kwargs: object) -> _UppercaseAbsence:
            return _UppercaseAbsence()

        monkeypatch.setattr(
            "oo_ratchet.core.adapters.gitrepo.subprocess.run", _fake_run
        )
        assert repo.exists_at(base, "x.py") is False

    def test_malformed_ref_raises_giterror_not_false(self, gfx: GitFixture) -> None:
        # A well-formed-but-nonexistent sha and a truly malformed ref both
        # exit 128, but git's stderr distinguishes them: the former reads
        # "does not exist in"/"exists on disk, but not in" (indistinguishable
        # from real absence, and correctly treated as absent), while the
        # latter -- an unparseable ref -- reads "invalid object name" and
        # must raise rather than be swallowed as "not present".
        gfx.write_source("x = 1\n")
        gfx.commit("base")
        repo = repo_at(gfx.root)
        with pytest.raises(GitError):
            repo.exists_at("bad..ref**", "pkg/a.py")

    def test_non_utf8_git_output_fails_closed_as_giterror(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `text=True` decodes git's output as UTF-8; non-UTF8 bytes (a binary
        # path in the error message, an unusual locale) must fail closed as
        # GitError, not crash the gate with an uncaught UnicodeDecodeError.
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)

        def _raise_unicode_error(*_args: object, **_kwargs: object) -> None:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        monkeypatch.setattr(
            "oo_ratchet.core.adapters.gitrepo.subprocess.run", _raise_unicode_error
        )
        with pytest.raises(GitError):
            repo.exists_at(base, "pkg/a.py")


class TestGitRepoArchivePaths:
    """``archive_paths`` fails closed on a bad ref or an unwritable destination."""

    def test_bad_ref_raises(self, gfx: GitFixture, tmp_path: Path) -> None:
        gfx.write_source("x = 1\n")
        gfx.commit("base")
        repo = repo_at(gfx.root)
        dest = tmp_path / "out"
        dest.mkdir()
        with pytest.raises(GitError):
            repo.archive_paths("0" * 40, ["pkg/a.py"], dest)

    def test_missing_dest_is_created(self, gfx: GitFixture, tmp_path: Path) -> None:
        # tarfile.extractall creates a missing destination directory itself
        # (unlike `tar -x -C`, which requires it to pre-exist).
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)
        dest = tmp_path / "does-not-exist"
        repo.archive_paths(base, ["pkg/a.py"], dest)
        assert (dest / "pkg" / "a.py").read_text() == "x = 1\n"

    def test_unwritable_dest_raises(self, gfx: GitFixture, tmp_path: Path) -> None:
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)
        dest = tmp_path / "blocked"
        dest.write_text("a file, not a directory")
        with pytest.raises(GitError):
            repo.archive_paths(base, ["pkg/a.py"], dest)

    def test_empty_paths_is_a_no_op(self, gfx: GitFixture, tmp_path: Path) -> None:
        gfx.write_source("x = 1\n")
        base = gfx.commit("base")
        repo = repo_at(gfx.root)
        dest = tmp_path / "out"
        dest.mkdir()
        repo.archive_paths(base, [], dest)
        assert list(dest.iterdir()) == []


class TestRelax:
    """``relax`` records an audited, justified ceiling for one file's real rise."""

    def test_relax_waives_the_regression(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        relax_outcome = gfx.relax(base, "reason", allow_ci_write=True)
        assert relax_outcome.exit_code == 0
        check_outcome = gfx.check(base_ref=base, require_base=True)
        assert check_outcome.exit_code == 0
        assert any("waived" in line for line in check_outcome.lines)

    def test_relax_requires_justification(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        outcome = gfx.relax(base, "   ", allow_ci_write=True)
        assert outcome.exit_code == 1
        assert any("--justify" in line for line in outcome.lines)

    def test_relax_refuses_when_nothing_rose(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        outcome = gfx.relax(base, "reason", allow_ci_write=True)
        assert outcome.exit_code == 1
        assert any("nothing to relax" in line for line in outcome.lines)

    def test_relax_never_covers_a_larger_future_rise(self, gfx: GitFixture) -> None:
        # A ceiling caps the file's TOTAL count, not the size of one rise --
        # growing the SAME file further beyond the ceiling must not ride the
        # earlier relaxation for free.
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        gfx.relax(base, "reason", allow_ci_write=True)
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\nz = 3  # noqa\n")
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("+1 unwaived" in line for line in outcome.lines)

    def test_relax_stops_covering_once_the_base_absorbs_it(
        self, gfx: GitFixture
    ) -> None:
        # Regression test: a ceiling must not become standing headroom once
        # the relaxed change merges and the comparison base itself already
        # carries the elevated count -- a LATER, unrelated rise in the same
        # file must be fully unwaived, not silently absorbed by the old
        # ceiling.
        gfx.write_source("x = 1  # noqa\n")
        pre_relax = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        gfx.relax(pre_relax, "reason", allow_ci_write=True)
        merged = gfx.commit("merge the relaxed change")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\nz = 3  # noqa\n")
        outcome = gfx.check(base_ref=merged, require_base=True)
        assert outcome.exit_code == 1
        assert any("+1 unwaived" in line for line in outcome.lines)
        assert not any("waived" in line for line in outcome.lines[:3])

    def test_relax_blocked_in_ci(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        outcome = gfx.relax(base, "reason", allow_ci_write=False)
        assert outcome.exit_code == 1
        assert any("GITHUB_ACTIONS" in line for line in outcome.lines)

    def test_relax_fails_hard_on_unresolvable_base(self, gfx: GitFixture) -> None:
        # Unlike check(), relax() must never report success while writing
        # nothing -- check()'s bootstrap-pass verdicts are for a read-only
        # comparison and must not leak into a write command's exit code.
        gfx.write_source("x = 1  # noqa\n")
        gfx.commit("base")
        outcome = gfx.relax("0" * 40, "reason", allow_ci_write=True)
        assert outcome.exit_code == 1
        assert not (gfx.root / ".suppression-relax.json").exists()

    def test_relax_fails_hard_on_absent_base_tree(self, gfx: GitFixture) -> None:
        (gfx.root / "README.md").write_text("placeholder\n")
        base = gfx.commit("base before pkg existed")
        gfx.write_source("x = 1  # noqa\n")
        gfx.commit("add pkg")
        outcome = gfx.relax(base, "reason", allow_ci_write=True)
        assert outcome.exit_code == 1
        assert not (gfx.root / ".suppression-relax.json").exists()


class TestSuppressionRelaxLedger:
    """The relax ledger's own load/save round-trip and fail-closed parsing."""

    @staticmethod
    def _ledger_path(gfx: GitFixture, entry: dict[str, object]) -> Path:
        path = gfx.root / ".suppression-relax.json"
        path.write_text(json.dumps([entry]))
        return path

    def test_corrupt_ledger_raises_typed_error(self, gfx: GitFixture) -> None:
        path = gfx.root / ".suppression-relax.json"
        path.write_text("{ not valid json")
        with pytest.raises(StateError):
            JsonLedger(path)

    def test_non_list_ledger_raises_typed_error(self, gfx: GitFixture) -> None:
        path = gfx.root / ".suppression-relax.json"
        path.write_text('{"file": "a.py"}')
        with pytest.raises(StateError):
            JsonLedger(path)

    @pytest.mark.parametrize("ceiling", [0, True, 2.9])
    def test_bad_ceiling_raises_not_coerced(
        self, gfx: GitFixture, ceiling: object
    ) -> None:
        # bool is an int subclass and 2.9 is not an integer: neither may be
        # coerced into an audited ceiling.
        entry = {"file": "a.py", "ceiling": ceiling, "justify": "x", "added_at": "t"}
        with pytest.raises(StateError):
            JsonLedger(self._ledger_path(gfx, entry))

    def test_absent_ledger_has_no_ceiling(self, gfx: GitFixture) -> None:
        path = gfx.root / ".suppression-relax.json"
        assert JsonLedger(path).ledger().ceiling("a.py") is None

    def test_round_trips_through_disk(self, gfx: GitFixture) -> None:
        path = gfx.root / ".suppression-relax.json"
        JsonLedger(path).add("a.py", 2, "reason")
        reloaded = JsonLedger(path).ledger()
        assert reloaded.ceiling("a.py") == 2
        assert reloaded.ceiling("missing.py") is None


class TestUpdateNeverLoosen:
    """update() writes decreases but refuses any net increase in the total."""

    def test_update_refuses_increase(self, gfx: GitFixture) -> None:
        # A rising total is refused and nothing is written, mirroring the OO and
        # coupling writers that refuse a per-metric regression.
        gfx.write_source("x = 1  # noqa\n")
        gfx.update(allow_ci_write=True)  # bootstrap total 1
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")  # now 2
        outcome = gfx.update(allow_ci_write=True)
        assert outcome.exit_code == 1
        assert any("never loosens" in line for line in outcome.lines)
        data = json.loads((gfx.root / ".suppression-baseline.json").read_text())
        assert data["total"] == 1  # unchanged: the increase wrote nothing

    def test_update_writes_decrease(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        gfx.update(allow_ci_write=True)  # bootstrap total 2
        gfx.write_source("x = 1  # noqa\n")  # now 1
        outcome = gfx.update(allow_ci_write=True)
        assert outcome.exit_code == 0
        data = json.loads((gfx.root / ".suppression-baseline.json").read_text())
        assert data["total"] == 1

    def test_update_rewrites_equal_total(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        gfx.update(allow_ci_write=True)  # bootstrap total 1
        outcome = gfx.update(allow_ci_write=True)
        assert outcome.exit_code == 0

    def test_first_adoption_bootstraps_any_total(self, gfx: GitFixture) -> None:
        # No in-tree baseline: the first update writes whatever the current total
        # is, matching the coupling/OO writers that bootstrap absent a baseline.
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")  # total 2, no baseline
        outcome = gfx.update(allow_ci_write=True)
        assert outcome.exit_code == 0
        data = json.loads((gfx.root / ".suppression-baseline.json").read_text())
        assert data["total"] == 2


class TestSuppressionFailClosed:
    """Base-commit authority, require-base, and controlled errors."""

    def test_in_tree_edit_cannot_launder_rising_count(self, gfx: GitFixture) -> None:
        # A PR adds a suppression AND rewrites the in-tree baseline to match. The
        # check rescans the base commit's real source, so the rise is still
        # caught regardless of what the laundered in-tree blob says.
        gfx.write_source("x = 1  # noqa\n")
        base = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")  # now 2
        gfx.update(allow_ci_write=True)  # launder the in-tree baseline to total 2
        gfx.commit("add suppression and launder the in-tree baseline")
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("increased" in line for line in outcome.lines)

    def test_require_base_unresolvable_fails_closed(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        gfx.commit("base")
        outcome = gfx.check(base_ref="0" * 40, require_base=True)
        assert outcome.exit_code == 1
        assert any("--require-base" in line for line in outcome.lines)

    def test_unresolvable_base_with_baseline_fails_closed(
        self, gfx: GitFixture
    ) -> None:
        # No base resolvable + in-tree baseline present + not require_base: match
        # the OO and coupling ratchets -- hard-fail rather than trust the
        # hand-editable in-tree file. Consistent across all three ratchets.
        gfx.write_source("x = 1  # noqa\n")
        gfx.update(allow_ci_write=True)
        gfx.commit("base")
        outcome = gfx.check(base_ref="0" * 40, require_base=False)
        assert outcome.exit_code == 1
        assert any("origin/main" in line for line in outcome.lines)

    def test_corrupt_baseline_raises_typed_error(self, gfx: GitFixture) -> None:
        # A corrupt in-tree baseline is parsed eagerly at construction and raises
        # the typed error rather than a JSONDecodeError traceback.
        gfx.write_baseline_text("{ not valid json")
        with pytest.raises(StateError):
            JsonTallyStore(gfx.root / ".suppression-baseline.json")

    def test_corrupt_baseline_is_controlled_nonzero_via_cli(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gfx.write_source("x = 1  # noqa\n")
        gfx.write_baseline_text("{ not valid json")
        gfx.commit("corrupt baseline")
        # The corrupt in-tree baseline raises at construction; the CLI catches the
        # typed error and returns a clean non-zero exit.
        assert main(["pkg", "--check"]) == 1

    def test_non_dict_in_tree_baseline_raises_typed_error(
        self, gfx: GitFixture
    ) -> None:
        gfx.write_baseline_text("[1, 2, 3]")
        with pytest.raises(StateError):
            JsonTallyStore(gfx.root / ".suppression-baseline.json")

    def test_as_int_coerces_nan_and_inf_to_zero(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf"), "x"):
            assert TallyFormat.total({"total": bad}) == 0
        assert TallyFormat.total({"total": 5}) == 5
        assert TallyFormat.total({}) == 0

    def test_as_int_rejects_bool(self) -> None:
        # bool is an int subclass; a bool count is invalid data -> 0, never
        # coerced to 1 (which would INFLATE the baseline, a fail-open). This
        # coercion still guards ``update()``'s in-tree ``_refuse_increase`` read.
        assert TallyFormat.total({"total": True}) == 0
        assert TallyFormat.total({"total": False}) == 0

    def test_non_utf8_baseline_raises_typed_error(self, gfx: GitFixture) -> None:
        # A non-UTF8 baseline file raises UnicodeDecodeError on read_text; _load
        # must turn it into the typed error, not a traceback.
        path = gfx.root / ".suppression-baseline.json"
        path.write_bytes(b"\xff\xfe\x00")
        with pytest.raises(StateError):
            JsonTallyStore(path)

    def test_non_utf8_source_is_controlled_nonzero_via_cli(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A non-UTF8 .py file raises UnicodeDecodeError on read_text; the CLI must
        # surface a controlled non-zero, not a traceback and not a silent skip.
        gfx.write_source("x = 1\n")
        (gfx.root / "pkg" / "bad.py").write_bytes(b"\xff\xfe# noqa\n")
        assert main(["pkg", "--json"]) == 1

    def test_scanner_propagates_unreadable_file(self, gfx: GitFixture) -> None:
        # An unreadable path that matches *.py (here a directory named like a
        # module) must raise, not be silently skipped -- skipping would
        # undercount a file's suppressions and let a real rise pass (fail-open).
        gfx.write_source("x = 1\n")
        (gfx.root / "pkg" / "isdir.py").mkdir()
        with pytest.raises(OSError):
            Scanner(gfx.root / "pkg", gfx.root)

    def test_unreadable_file_is_controlled_nonzero_via_cli(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gfx.write_source("x = 1\n")
        (gfx.root / "pkg" / "isdir.py").mkdir()
        # The OSError surfaces as a clean non-zero through the CLI, not a
        # traceback -- and not a silent skip.
        assert main(["pkg", "--json"]) == 1


class TestCiWriteGuard:
    """update() refuses to run under GITHUB_ACTIONS without --allow-ci-write."""

    def test_update_blocked_in_ci(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        gfx.write_source("x = 1  # noqa\n")
        outcome = gfx.update(allow_ci_write=False)
        assert outcome.exit_code == 1
        assert any("GITHUB_ACTIONS" in line for line in outcome.lines)

    def test_update_allowed_with_flag_in_ci(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        gfx.write_source("x = 1  # noqa\n")
        outcome = gfx.update(allow_ci_write=True)
        assert outcome.exit_code == 0


class TestPyproject:
    """per_file_ignores counting fails closed on a broken pyproject.toml."""

    def test_absent_pyproject_is_zero(self, gfx: GitFixture) -> None:
        # No pyproject.toml legitimately contributes 0 -- not a failure.
        counter = PerFileIgnoresCounter(gfx.root / "pyproject.toml")
        assert counter.total == 0

    def test_invalid_toml_raises(self, gfx: GitFixture) -> None:
        (gfx.root / "pyproject.toml").write_text("this is [ not valid toml")
        with pytest.raises(PyprojectError):
            PerFileIgnoresCounter(gfx.root / "pyproject.toml")

    def test_invalid_pyproject_is_controlled_nonzero_via_cli(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An existing-but-invalid pyproject.toml would undercount per_file_ignores;
        # the CLI turns it into a controlled non-zero, not a silent zero.
        gfx.write_source("x = 1\n")
        (gfx.root / "pyproject.toml").write_text("this is [ not valid toml")
        assert main(["pkg", "--json"]) == 1

    def test_absent_pyproject_passes_via_cli(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gfx.write_source("x = 1\n")
        assert main(["pkg", "--json"]) == 0

    def test_no_ignores_section_is_zero(self, gfx: GitFixture) -> None:
        # A valid pyproject with no per-file-ignores section legitimately -> 0.
        (gfx.root / "pyproject.toml").write_text("[tool.ruff]\nline-length = 88\n")
        assert PerFileIgnoresCounter(gfx.root / "pyproject.toml").total == 0

    def test_valid_ignores_are_counted(self, gfx: GitFixture) -> None:
        (gfx.root / "pyproject.toml").write_text(
            "[tool.ruff.lint.per-file-ignores]\n"
            '"a.py" = ["E501", "F401"]\n'
            '"b.py" = ["N801"]\n'
        )
        assert PerFileIgnoresCounter(gfx.root / "pyproject.toml").total == 3

    def test_ignores_not_a_table_raises(self, gfx: GitFixture) -> None:
        # per-file-ignores EXISTS but is a string, not a table -> fail closed.
        (gfx.root / "pyproject.toml").write_text(
            '[tool.ruff.lint]\nper-file-ignores = "oops"\n'
        )
        with pytest.raises(PyprojectError):
            PerFileIgnoresCounter(gfx.root / "pyproject.toml")

    def test_ignores_codes_not_a_list_raises(self, gfx: GitFixture) -> None:
        # A per-file entry whose codes value isn't a list is corrupt -> fail closed.
        (gfx.root / "pyproject.toml").write_text(
            '[tool.ruff.lint.per-file-ignores]\n"a.py" = "E501"\n'
        )
        with pytest.raises(PyprojectError):
            PerFileIgnoresCounter(gfx.root / "pyproject.toml")

    def test_non_table_ancestor_is_zero(self, gfx: GitFixture) -> None:
        # A malformed non-table ancestor means no section to count -> 0, no crash.
        (gfx.root / "pyproject.toml").write_text('tool = "not a table"\n')
        assert PerFileIgnoresCounter(gfx.root / "pyproject.toml").total == 0


class TestRepoRootResolution:
    """The CLI anchors the baseline and pyproject to the repo root, not cwd."""

    def test_cli_resolves_repo_root_from_subdir(
        self, gfx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # From a subdirectory, the CLI resolves the repo root via GitRepo and
        # reads the ROOT .suppression-baseline.json. With cwd anchoring it would
        # miss the baseline and wrongly bootstrap-pass; anchored, the
        # unresolvable-base + baseline-present case fails closed.
        gfx.write_source("x = 1  # noqa\n")
        gfx.update(allow_ci_write=True)  # writes repo-root .suppression-baseline.json
        gfx.commit("base with root baseline")
        monkeypatch.chdir(gfx.root / "pkg")
        assert main([".", "--check", "--base-ref", "0" * 40]) == 1


def test_cli_json_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(WITH_SUPPRESSIONS)
    monkeypatch.chdir(tmp_path)
    assert main(["pkg", "--json"]) == 0


class TestMergedWaiverRetires:
    """PL-1141: a merged ceiling covers nothing, so cleanups become real floors."""

    @staticmethod
    def _relax(gfx: GitFixture, base: str, justify: str = "reason") -> Result:
        return gfx.relax(base, justify, allow_ci_write=True)

    def _merge_waiver_then_cleanup(self, gfx: GitFixture) -> str:
        gfx.write_source("x = 1  # noqa\n")
        pre = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\nz = 3  # noqa\n")
        assert self._relax(gfx, pre).exit_code == 0
        gfx.commit("merge the relaxed change")
        gfx.write_source("x = 1\n")
        return gfx.commit("cleanup")

    def test_waiver_applies_on_post_merge_tripwire_base(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        pre = gfx.commit("base")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        self._relax(gfx, pre)
        gfx.commit("merge the relaxed change")
        outcome = gfx.check(base_ref=pre, require_base=True)
        assert outcome.exit_code == 0
        assert any("waived" in line for line in outcome.lines)

    def test_regrowth_after_cleanup_is_not_waived(self, gfx: GitFixture) -> None:
        cleanup = self._merge_waiver_then_cleanup(gfx)
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        outcome = gfx.check(base_ref=cleanup, require_base=True)
        assert outcome.exit_code == 1
        assert any("+2 unwaived" in line for line in outcome.lines)

    def test_fresh_relax_after_cleanup_waives_again(self, gfx: GitFixture) -> None:
        cleanup = self._merge_waiver_then_cleanup(gfx)
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        assert self._relax(gfx, cleanup, justify="new reason").exit_code == 0
        assert gfx.check(base_ref=cleanup, require_base=True).exit_code == 0

    def test_merged_ledger_only_entry_grants_no_headroom(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        entry = {
            "file": str(gfx.root / "pkg" / "a.py"),
            "ceiling": 5,
            "justify": "hand-written",
            "added_at": "2026-01-01T00:00:00Z",
        }
        (gfx.root / ".suppression-relax.json").write_text(json.dumps([entry]))
        merged = gfx.commit("ledger-only change")
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\n")
        outcome = gfx.check(base_ref=merged, require_base=True)
        assert outcome.exit_code == 1
        assert any("+1 unwaived" in line for line in outcome.lines)

    def test_malformed_base_ledger_fails_closed(self, gfx: GitFixture) -> None:
        gfx.write_source("x = 1  # noqa\n")
        (gfx.root / ".suppression-relax.json").write_text("{ not json")
        base = gfx.commit("bad ledger")
        (gfx.root / ".suppression-relax.json").write_text("[]")
        outcome = gfx.check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert "unreadable suppression relax ledger" in outcome.lines[0]

    def test_same_second_relax_to_old_ceiling_is_fresh(self, gfx: GitFixture) -> None:
        cleanup = self._merge_waiver_then_cleanup(gfx)
        gfx.write_source("x = 1  # noqa\ny = 2  # noqa\nz = 3  # noqa\n")
        assert self._relax(gfx, cleanup).exit_code == 0
        assert gfx.check(base_ref=cleanup, require_base=True).exit_code == 0

    def test_base_without_ledger_clears_retirements(self) -> None:
        entry = Ceiling("a.py", 2, "reason", "t")
        ledger = Ledger({"a.py": entry})
        assert ledger.surviving(Ledger({"a.py": entry})).ceiling("a.py") is None
        assert ledger.surviving(None).ceiling("a.py") == 2
        changed = Ledger({"a.py": Ceiling("a.py", 2, "reason", "later")})
        assert ledger.surviving(changed).ceiling("a.py") == 2
