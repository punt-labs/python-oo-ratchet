"""A namespace split changes physical ownership, never import identity or debt."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main
from oo_ratchet.coupling.cli import SPEC as COUPLING
from oo_ratchet.coupling.graph import ImportGraph
from oo_ratchet.coupling.layout import PackageLayout
from oo_ratchet.coupling.scorer import CouplingScorer
from oo_ratchet.design.scan import DesignScanner
from oo_ratchet.gate_options import GateOptions
from oo_ratchet.layers.scan import LayerScan
from oo_ratchet.oo.scorer import Scorer
from oo_ratchet.source_history import SourceHistory
from oo_ratchet.source_set import SourceSelection
from oo_ratchet.suppression.scanner import Scanner

HEADER = "from __future__ import annotations\n"
CONFIG = """[tool.oo-ratchet.layers.a]
prefixes = ["a"]
imports = []
[tool.oo-ratchet.layers.b]
prefixes = ["b"]
imports = []
"""


def write(root: Path, name: str, code: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code)
    return path


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, SourceSelection]:
    source = tmp_path / "single/src/app"
    write(source, "a/__init__.py", HEADER)
    write(source, "b/__init__.py", HEADER)
    write(
        source,
        "a/core.py",
        HEADER + "from app.b.core import Beta\nclass Alpha:\n"
        "    def run(self) -> str:\n        return Beta().run()\n",
    )
    write(
        source,
        "b/core.py",
        HEADER + "from app.a.core import Alpha\nclass Beta:\n"
        "    def run(self) -> str:\n        return Alpha().run()\n",
    )
    project = tmp_path / "split"
    roots = tuple(project / f"packages/{name}/src/app" for name in ("a", "b"))
    for name, root in zip(("a", "b"), roots, strict=True):
        shutil.copytree(source / name, root / name)
    write(tmp_path / "single", "pyproject.toml", CONFIG)
    write(project, "pyproject.toml", CONFIG)
    return source, SourceSelection.from_roots(roots, "app", project)


def test_split_matches_entire_graph_cycles_metrics_and_layers(
    trees: tuple[Path, SourceSelection],
) -> None:
    single, split = trees
    before, after = PackageLayout(single), PackageLayout(split)
    a, b = ImportGraph.build(before), ImportGraph.build(after)
    assert a.edges == b.edges
    assert a.cycle_members() == b.cycle_members() == {"a.core", "b.core"}
    old, new = CouplingScorer(single), CouplingScorer(split)
    by_module_old = {
        before.key_for(Path(str(r["file"]))): {
            k: v for k, v in r.items() if k != "file"
        }
        for r in old.results
    }
    by_module_new = {
        after.key_for(Path(str(r["file"]))): {k: v for k, v in r.items() if k != "file"}
        for r in new.results
    }
    assert by_module_old == by_module_new
    assert old.summary == new.summary
    assert old.packages == new.packages
    assert (
        LayerScan(SourceSelection.from_roots((single,), "app")).edges
        == LayerScan(split).edges
    )
    assert {str(e) for e in LayerScan(split).edges} == {
        "app.a.core -> app.b.core",
        "app.b.core -> app.a.core",
    }
    assert LayerScan(split).problems == ()
    left = json.loads(DesignScanner(single).report.to_json())
    right = json.loads(DesignScanner(split).report.to_json())
    assert left["files_scanned"] == right["files_scanned"]
    assert left["counts"] == right["counts"]


def test_sources_are_deduplicated_and_keep_physical_baseline_keys(
    trees: tuple[Path, SourceSelection],
) -> None:
    _, source = trees
    duplicate = SourceSelection.from_roots(
        (*source.roots, source.roots[0]), "app", source.project
    )
    root = source.project
    assert root is not None
    assert Scorer(source, root).results == Scorer(duplicate, root).results
    assert CouplingScorer(source, root).files == frozenset(
        str(p.relative_to(root)) for p in SourceSelection.files(source)
    )
    write(source.roots[0], "a/suppressed.py", HEADER + "x = 1  # noqa: F841\n")
    assert "packages/a/src/app/a/suppressed.py" in Scanner(source, root).report.by_file


def test_conflicting_namespace_portions_are_rejected(tmp_path: Path) -> None:
    roots = tuple(tmp_path / name / "app" for name in ("one", "two"))
    for root in roots:
        write(root, "same.py", HEADER)
    with pytest.raises(ValueError, match=r"duplicate module app\.same"):
        SourceSelection.from_roots(roots, "app")


@pytest.mark.parametrize("namespace", ["", "a.b", "class", "a-b"])
def test_invalid_namespace_is_rejected(tmp_path: Path, namespace: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        SourceSelection.from_roots((tmp_path,), namespace)


@pytest.mark.parametrize("gate", ["oo", "coupling", "suppressions", "design", "layers"])
def test_bad_configured_root_fails_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    monkeypatch.chdir(tmp_path)
    write(
        tmp_path,
        "pyproject.toml",
        '[tool.oo-ratchet]\nnamespace="app"\nroots=["missing/*/app"]\n',
    )
    with pytest.raises(SystemExit) as error:
        main([gate, "--json"])
    assert error.value.code == 2
    assert not list(tmp_path.glob(".*baseline*"))


def test_config_globs_and_explicit_roots_give_identical_reports(
    trees: tuple[Path, SourceSelection],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, source = trees
    assert source.project is not None
    monkeypatch.chdir(source.project)
    write(
        source.project,
        "pyproject.toml",
        '[tool.oo-ratchet]\nnamespace="app"\nroots=["packages/*/src/app"]\n' + CONFIG,
    )
    assert main(["coupling", "--json"]) in (0, 1)
    configured = capsys.readouterr().out
    assert main(
        ["coupling", "--namespace", "app", *map(str, source.roots), "--json"]
    ) in (0, 1)
    assert capsys.readouterr().out == configured


def test_legacy_module_matches_existing_oo_baseline_golden(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    baseline = json.loads((repo / "tests/golden_layout_oo.json").read_text())
    fixture = write(
        tmp_path, "layout.py", (repo / "tests/golden_layout.py.txt").read_text()
    )
    row = Scorer(fixture, tmp_path).results[0]
    assert {k: row[k] for k in baseline} == baseline
    coupling = json.loads((repo / "tests/golden_layout_coupling.json").read_text())
    metrics = CouplingScorer(fixture, tmp_path).results[0]
    assert {k: metrics[k] for k in coupling} == coupling


@pytest.mark.parametrize("roots", [(), ("app",)])
def test_empty_namespace_has_no_silent_success(
    tmp_path: Path, roots: tuple[str, ...]
) -> None:
    for name in roots:
        (tmp_path / name).mkdir()
    with pytest.raises(ValueError, match=r"at least one|no Python"):
        SourceSelection.from_roots(tuple(tmp_path / name for name in roots), "app")


def test_bad_config_table_is_a_cli_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write(tmp_path, "pyproject.toml", "tool = 1\n")
    with pytest.raises(SystemExit) as error:
        main(["coupling", "--namespace", "app", "missing/app"])
    assert error.value.code == 2


def test_absent_historical_root_does_not_select_unrelated_namespace(
    trees: tuple[Path, SourceSelection], tmp_path: Path
) -> None:
    _, source = trees
    assert source.project is not None
    tree = tmp_path / "base"
    write(tree, "app/unrelated.py", HEADER)
    target = SourceHistory(source.target).at_base(source.project, tree, {})
    assert not SourceSelection(target).anchor.exists()


def test_resolved_namespace_is_passed_through_unchanged(
    trees: tuple[Path, SourceSelection],
) -> None:
    _, source = trees
    options = GateOptions.parse(
        COUPLING, ["--namespace", "app", *map(str, source.roots)]
    )
    assert isinstance(options.src, SourceSelection)
    assert SourceSelection(options.src) is options.src
    assert PackageLayout(options.src)._source is options.src


def test_resolved_legacy_file_preserves_single_file_metrics(tmp_path: Path) -> None:
    file = write(tmp_path, "app/a.py", HEADER + "from .b import Beta\n")
    write(tmp_path, "app/b.py", HEADER + "class Beta: pass\n")
    assert CouplingScorer(file).results == CouplingScorer(SourceSelection(file)).results
