"""Regressions for the Qodo review findings on PR #1."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import oo_ratchet.coupling
import oo_ratchet.oo
import oo_ratchet.suppression
from oo_ratchet.core.domain.tallies import Tally
from oo_ratchet.coupling.audit import CouplingAudit, CouplingAuditError
from oo_ratchet.coupling.gitio import GitError as CouplingGitError
from oo_ratchet.coupling.gitio import GitRepo as CouplingGitRepo
from oo_ratchet.coupling.imports import ImportResolver
from oo_ratchet.oo.audit import AuditError, AuditLog
from oo_ratchet.oo.gitio import GitError as OoGitError
from oo_ratchet.oo.gitio import GitRepo
from oo_ratchet.oo.gitio import GitRepo as OoGitRepo
from oo_ratchet.oo.scorer import Scorer
from oo_ratchet.source_set import Source
from oo_ratchet.suppression.patterns import FileSuppressions
from oo_ratchet.suppression.scanner import Scanner

if TYPE_CHECKING:
    from tests.conftest import GitSandbox

_SRC = (
    "from __future__ import annotations\n\n\n"
    "class Thing:\n"
    "    def name(self) -> str:\n"
    '        return "thing"\n'
)


def _imports(source: str, own: str, *, is_package: bool = False) -> set[str]:
    modules = frozenset({"sub", "sub.x", "other"})
    resolver = ImportResolver(own, modules, "pkg", is_package=is_package)
    return resolver.internal_imports(ast.parse(source))


class TestImportResolution:
    def test_absolute_from_import_resolves_the_imported_module(self) -> None:
        assert _imports("from pkg.sub import x\n", "other") == {"sub", "sub.x"}
        assert _imports("from pkg import sub\n", "other") == {"sub"}

    def test_relative_imports_in_package_init_resolve_against_the_package(
        self,
    ) -> None:
        assert _imports("from . import x\n", "sub", is_package=True) == {"sub.x"}
        assert _imports("from .x import y\n", "sub", is_package=True) == {"sub.x"}


def test_scanner_honors_a_coding_cookie(tmp_path: Path) -> None:
    src = tmp_path / "latin.py"
    src.write_bytes(b"# -*- coding: latin-1 -*-\nx = '\xe9'  # noqa\n")
    assert Scanner(src, tmp_path).report.total == 1


@pytest.mark.parametrize(
    ("parse", "error"),
    [(AuditLog._parse, AuditError), (CouplingAudit._parse, CouplingAuditError)],
)
def test_non_object_audit_line_is_a_controlled_audit_error(
    parse: object, error: type[Exception]
) -> None:
    assert callable(parse)
    with pytest.raises(error):
        parse("[]")


def test_single_file_target_records_an_error_row(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_bytes(b"\xff\xfe x = 1\n")
    results = Scorer(bad, tmp_path).results
    assert len(results) == 1
    assert "error" in results[0]


@pytest.mark.parametrize(
    ("source", "category", "count"),
    [
        ("# type: ignore\nx = 1\n", "file_level", 1),
        ("# ruff: noqa\nx = 1\n", "file_level", 1),
        ('"""Doc."""\n# mypy: ignore-errors\n', "file_level", 1),
        ("x = 1  # type: ignore\n", "file_level", 0),
        ("x = 1  # type: ignore\n", "type_ignore", 1),
        ("# pylint: skip-file\nx = 1\n", "file_level", 1),
        ("x = 1\n# pylint: disable=invalid-name\ny = 2\n", "file_level", 1),
        ("# pyright: reportAny=false\nx = 1\n", "file_level", 1),
        ("x = 1  # type: ignore  # noqa  # ruff: noqa\n", "type_ignore", 1),
        ("x = 1  # type: ignore  # noqa  # ruff: noqa\n", "noqa", 1),
        ("x = 1  # type: ignore  # noqa  # ruff: noqa\n", "file_level", 1),
    ],
)
def test_file_level_suppressions_are_counted(
    source: str, category: str, count: int
) -> None:
    assert FileSuppressions("m.py", source).count(category) == count


@pytest.mark.parametrize(
    ("gate", "extra"),
    [
        (oo_ratchet.oo.main, ["--allow-no-improvement"]),
        (oo_ratchet.coupling.main, []),
        (oo_ratchet.suppression.main, []),
    ],
)
def test_tripwire_fails_when_main_has_no_baseline(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    gate: object,
    extra: list[str],
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    git_sandbox.write("README.md", "x\n")
    pre = git_sandbox.commit("pre")
    git_sandbox.write("src/pkg/__init__.py", "")
    git_sandbox.write("src/pkg/thing.py", _SRC)
    git_sandbox.commit("source without baselines")
    assert callable(gate)
    args = ["src/pkg", "--check", "--base-ref", pre, "--require-base", "--tripwire"]
    assert gate([*args, *extra]) == 1


def test_diff_keeps_non_ascii_python_paths(git_sandbox: GitSandbox) -> None:
    git_sandbox.write("README.md", "x\n")
    base = git_sandbox.commit("base")
    git_sandbox.write("src/pkg/\u00f1.py", _SRC)
    git_sandbox.commit("non-ascii module")
    touched = GitRepo(Path(git_sandbox.root)).diff(base).python_files()
    assert "src/pkg/\u00f1.py" in touched


def test_coupling_update_audits_removed_paths(
    git_sandbox: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    git_sandbox.write("src/pkg/__init__.py", "")
    git_sandbox.write("src/pkg/a.py", _SRC)
    git_sandbox.write("src/pkg/b.py", _SRC)
    args = ["src/pkg", "--rebaseline", "--allow-ci-write"]
    assert oo_ratchet.coupling.main(args) == 0
    base = git_sandbox.commit("base")
    (Path(git_sandbox.root) / "src/pkg/b.py").unlink()
    oo_ratchet.coupling.main(
        ["src/pkg", "--update", "--base-ref", base, "--allow-ci-write"]
    )
    audit = Path(git_sandbox.root) / ".oo-coupling-audit.jsonl"
    last = json.loads(audit.read_text().splitlines()[-1])
    assert last["removed"] == ["src/pkg/b.py"]


def test_suppression_rescan_of_dot_target_keys_like_the_live_scan(
    git_sandbox: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    git_sandbox.write("pkg/a.py", "x = 1  # noqa\n")
    base = git_sandbox.commit("base")
    from oo_ratchet.core.adapters.gitrepo import GitRepo as CoreGit
    from oo_ratchet.core.adapters.tallyrepo import TallyRepo

    def scan(target: Source, project: Path) -> Tally:
        report = Scanner(target, project).report
        return Tally(report.by_category, report.by_file)

    git = CoreGit(Path(), ".suppression-baseline.json", ".suppression-audit.jsonl")
    history = TallyRepo(git, Path(), Path(), scan, ".suppression-relax.json")
    rescanned = history.tally_at(base)
    assert rescanned is not None
    assert set(rescanned.by_file) == set(Scanner(Path(), Path()).report.by_file)


def test_root_init_relative_import_keeps_the_submodule_edge() -> None:
    modules = frozenset({"__init__", "sub", "sub.mod"})
    resolver = ImportResolver("__init__", modules, "pkg", is_package=True)
    tree = ast.parse("from .sub.mod import X\n")
    assert resolver.internal_imports(tree) == {"sub.mod"}


def test_scanner_counts_non_latin_cookie_files(tmp_path: Path) -> None:
    src = tmp_path / "sjis.py"
    src.write_bytes(
        "# -*- coding: shift_jis -*-\nx = '\u8868'  # noqa\n".encode("shift_jis")
    )
    counts = Scanner(src, tmp_path).report
    assert counts.total == 1


def test_unscorable_single_file_fails_instead_of_viewing_clean(
    git_sandbox: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    git_sandbox.write("src/pkg/thing.py", _SRC)
    assert oo_ratchet.oo.main(["src/pkg", "--rebaseline", "--allow-ci-write"]) == 0
    git_sandbox.write("src/pkg/thing.py", "def broken(:\n")
    target = "src/pkg/thing.py"
    assert oo_ratchet.oo.main([target]) == 1
    assert oo_ratchet.oo.main([target, "--rebaseline", "--allow-ci-write"]) == 1
    assert (
        "src/pkg/thing.py" in (Path(git_sandbox.root) / ".oo-baseline.json").read_text()
    )


@pytest.mark.parametrize(
    ("repo_cls", "error"),
    [(OoGitRepo, OoGitError), (CouplingGitRepo, CouplingGitError)],
)
def test_non_utf8_git_output_raises_instead_of_reading_as_absent(
    repo_cls: type[OoGitRepo] | type[CouplingGitRepo],
    error: type[Exception],
    tmp_path: Path,
) -> None:
    emit = "import sys; sys.stdout.buffer.write(b'src/\\xff.py')"
    with pytest.raises(error, match="not valid UTF-8"):
        repo_cls._run([sys.executable, "-c", emit], cwd=tmp_path)


def test_unscorable_single_file_still_shows_log_and_json(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    git_sandbox.write("src/pkg/thing.py", "def broken(:\n")
    assert oo_ratchet.oo.main(["src/pkg/thing.py", "--log"]) == 0
    capsys.readouterr()
    assert oo_ratchet.oo.main(["src/pkg/thing.py", "--json"]) == 1
    assert '"error"' in capsys.readouterr().out
